"""Local face/emotion analysis for wedding montage clip selection.

Uses OpenCV YuNet face detection (ONNX, auto-downloaded) plus lightweight
heuristics for smile, sharpness, and exposure. No paid APIs required.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

MODELS_DIR = Path(__file__).resolve().parent / "models"
YUNET_NAME = "face_detection_yunet_2026may.onnx"
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2026may.onnx"
)

# Optional MediaPipe landmarker (downloaded on demand if import succeeds).
FACE_LANDMARKER_NAME = "face_landmarker.task"
FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


@dataclass
class FrameMoment:
    t: float
    emotion_score: float
    smile: float
    face_count: int
    sharpness: float
    quality: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, dest)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc


def ensure_model(name: str, url: str) -> Path:
    path = MODELS_DIR / name
    if not path.exists() or path.stat().st_size < 1024:
        _download(url, path)
    return path


def ensure_yunet_model() -> Path:
    return ensure_model(YUNET_NAME, YUNET_URL)


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def sharpness_score(gray: np.ndarray) -> float:
    """Laplacian variance mapped to 0-1 (typical handheld wedding footage)."""
    if gray.size == 0:
        return 0.0
    small = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
    lap = cv2.Laplacian(small, cv2.CV_64F)
    var = float(lap.var())
    # Soft sigmoid: ~0 below 40, ~1 above 400 for 720p sources.
    return _clip01(var / (var + 120.0))


def exposure_score(gray: np.ndarray) -> float:
    """Penalize under/over exposure and highlight clipping."""
    if gray.size == 0:
        return 0.0
    mean = float(np.mean(gray))
    dark = float(np.mean(gray < 25))
    bright = float(np.mean(gray > 235))
    # Ideal mean luminance for skin/scenes ~95-145.
    mean_score = 1.0 - min(abs(mean - 120.0) / 120.0, 1.0)
    clip_penalty = min(1.0, dark * 2.5 + bright * 2.5)
    return _clip01(mean_score * (1.0 - 0.75 * clip_penalty))


def quality_score(sharpness: float, exposure: float) -> float:
    return _clip01(0.62 * sharpness + 0.38 * exposure)


def _mouth_roi_heuristic(face_gray: np.ndarray) -> float:
    """Fallback smile estimate from lower-face edges and aspect ratio."""
    h, w = face_gray.shape[:2]
    if h < 20 or w < 20:
        return 0.0
    mouth = face_gray[int(h * 0.58) : h, int(w * 0.15) : int(w * 0.85)]
    if mouth.size == 0:
        return 0.0
    mouth = cv2.GaussianBlur(mouth, (5, 5), 0)
    _, bw = cv2.threshold(mouth, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ys, xs = np.where(bw > 0)
    if len(xs) < 12:
        edges = cv2.Canny(mouth, 40, 120)
        return _clip01(float(np.mean(edges > 0)) * 2.2)
    aspect = (xs.max() - xs.min() + 1.0) / (ys.max() - ys.min() + 4.0)
    edge_density = float(np.mean(cv2.Canny(mouth, 35, 110) > 0))
    return _clip01(0.55 * min(aspect / 3.2, 1.0) + 0.45 * min(edge_density * 3.0, 1.0))


def smile_from_yunet(face: np.ndarray, frame_shape: tuple[int, ...]) -> float:
    """Estimate smile from YuNet landmarks (mouth corners + nose tip)."""
    x, y, w, h = face[:4]
    if w <= 1 or h <= 1:
        return 0.0
    _, nose_y, rcm_x, rcm_y, lcm_x, lcm_y = face[8:14]
    mouth_w = abs(float(rcm_x - lcm_x))
    width_ratio = mouth_w / max(float(w), 1.0)
    mouth_center_y = 0.5 * (float(rcm_y) + float(lcm_y))
    # Corners above mouth center on a smile (image y grows downward).
    corner_lift = (mouth_center_y - min(float(rcm_y), float(lcm_y))) / max(float(h), 1.0)
    nose_to_mouth = (mouth_center_y - float(nose_y)) / max(float(h), 1.0)
    width_score = _clip01((width_ratio - 0.28) / 0.22)
    lift_score = _clip01(corner_lift / 0.08)
    open_score = _clip01((nose_to_mouth - 0.18) / 0.22)
    return _clip01(0.45 * width_score + 0.35 * lift_score + 0.20 * open_score)


class FaceBackend:
    """OpenCV YuNet detector with optional MediaPipe landmark refinement."""

    def __init__(
        self,
        conf_threshold: float = 0.55,
        nms_threshold: float = 0.3,
        use_mediapipe: bool = False,
    ) -> None:
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.use_mediapipe = use_mediapipe
        self._detector: cv2.FaceDetectorYN | None = None
        self._input_size: tuple[int, int] | None = None
        self._landmarker = None

        if use_mediapipe:
            self._init_mediapipe()

    def _init_mediapipe(self) -> None:
        try:
            from mediapipe.tasks.python.core import base_options as base_options_module
            from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions
            import mediapipe as mp
        except ImportError:
            self.use_mediapipe = False
            return

        model_path = ensure_model(FACE_LANDMARKER_NAME, FACE_LANDMARKER_URL)
        options = FaceLandmarkerOptions(
            base_options=base_options_module.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=4,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)

    def _ensure_detector(self, width: int, height: int) -> cv2.FaceDetectorYN:
        size = (width, height)
        if self._detector is not None and self._input_size == size:
            return self._detector
        model = str(ensure_yunet_model())
        self._detector = cv2.FaceDetectorYN.create(
            model,
            "",
            size,
            self.conf_threshold,
            self.nms_threshold,
            5000,
        )
        self._detector.setInputSize(size)
        self._input_size = size
        return self._detector

    def detect(self, frame_bgr: np.ndarray) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        detector = self._ensure_detector(w, h)
        _, faces = detector.detect(frame_bgr)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        return faces

    def smile_mediapipe(self, frame_bgr: np.ndarray) -> float:
        if self._landmarker is None:
            return 0.0
        import mediapipe as mp

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return 0.0

        scores: list[float] = []
        for landmarks in result.face_landmarks:
            # Mouth corner / lip indices for blendshape-free geometry smile cue.
            upper_lip = landmarks[13]
            lower_lip = landmarks[14]
            left = landmarks[61]
            right = landmarks[291]
            mouth_w = abs(left.x - right.x)
            mouth_open = abs(upper_lip.y - lower_lip.y)
            corner_lift = 0.5 * (left.y + right.y) - lower_lip.y
            width_score = _clip01((mouth_w - 0.18) / 0.12)
            lift_score = _clip01((0.02 - corner_lift) / 0.05)
            open_score = _clip01((mouth_open - 0.015) / 0.04)
            scores.append(_clip01(0.5 * width_score + 0.35 * lift_score + 0.15 * open_score))
        return float(max(scores)) if scores else 0.0


def _face_smile(face: np.ndarray, face_gray: np.ndarray, frame_shape: tuple[int, ...]) -> float:
    yunet = smile_from_yunet(face, frame_shape)
    heuristic = _mouth_roi_heuristic(face_gray)
    return _clip01(0.72 * yunet + 0.28 * heuristic)


def analyze_frame(
    frame_bgr: np.ndarray,
    t: float,
    backend: FaceBackend,
) -> FrameMoment:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    sharp = sharpness_score(gray)
    exposure = exposure_score(gray)
    quality = quality_score(sharp, exposure)

    faces = backend.detect(frame_bgr)
    face_count = int(faces.shape[0])

    smile = 0.0
    if face_count > 0:
        face_scores = []
        for face in faces:
            x, y, w, h = face[:4].astype(int)
            x2, y2 = min(frame_bgr.shape[1], x + w), min(frame_bgr.shape[0], y + h)
            x, y = max(0, x), max(0, y)
            roi = gray[y:y2, x:x2]
            face_scores.append(_face_smile(face, roi, frame_bgr.shape))
        smile = float(max(face_scores))

    if backend.use_mediapipe and backend._landmarker is not None:
        mp_smile = backend.smile_mediapipe(frame_bgr)
        smile = _clip01(0.55 * smile + 0.45 * mp_smile)

    # Favor visible faces, genuine smiles, and usable frames.
    face_presence = _clip01(face_count / 2.0)
    emotion = _clip01(
        0.40 * smile + 0.20 * face_presence + 0.25 * quality + 0.15 * min(face_count, 3) / 3.0
    )
    return FrameMoment(
        t=float(t),
        emotion_score=emotion,
        smile=smile,
        face_count=face_count,
        sharpness=sharp,
        quality=quality,
    )


def analyze_video(
    video_path: str | Path,
    sample_fps: float = 2.0,
    max_seconds: float | None = None,
    resize_width: int = 960,
    conf_threshold: float = 0.55,
    use_mediapipe: bool = False,
) -> list[FrameMoment]:
    """Sample a video and return per-frame emotion/quality moments."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(path)

    backend = FaceBackend(conf_threshold=conf_threshold, use_mediapipe=use_mediapipe)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")

    native_fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    if native_fps <= 0:
        native_fps = 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / native_fps if frame_count > 0 else None
    if max_seconds is not None and duration is not None:
        duration = min(duration, max_seconds)

    step = max(1, int(round(native_fps / max(sample_fps, 0.5))))
    moments: list[FrameMoment] = []
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = frame_idx / native_fps
        if max_seconds is not None and t > max_seconds:
            break

        if frame_idx % step == 0:
            if resize_width > 0 and frame.shape[1] > resize_width:
                scale = resize_width / frame.shape[1]
                frame = cv2.resize(
                    frame,
                    (resize_width, int(frame.shape[0] * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            moments.append(analyze_frame(frame, t, backend))

        frame_idx += 1

    cap.release()
    return moments


def top_peaks(
    moments: list[FrameMoment],
    n: int = 10,
    min_gap: float = 0.75,
) -> list[FrameMoment]:
    """Return top emotional peaks with temporal non-max suppression."""
    ranked = sorted(moments, key=lambda m: m.emotion_score, reverse=True)
    picked: list[FrameMoment] = []
    for moment in ranked:
        if all(abs(moment.t - p.t) >= min_gap for p in picked):
            picked.append(moment)
        if len(picked) >= n:
            break
    return sorted(picked, key=lambda m: m.t)


def _format_ts(seconds: float) -> str:
    m, s = divmod(seconds, 60.0)
    return f"{int(m):02d}:{s:05.2f}"


def _demo(video: Path, use_mediapipe: bool = False) -> None:
    print(f"Analyzing {video.name} ...")
    moments = analyze_video(video, sample_fps=2.0, use_mediapipe=use_mediapipe)
    print(f"Sampled {len(moments)} frames")
    peaks = top_peaks(moments, n=8)
    print("\nTop emotional peaks:")
    for i, p in enumerate(peaks, 1):
        print(
            f"  {i}. t={_format_ts(p.t)}  emotion={p.emotion_score:.3f}  "
            f"smile={p.smile:.3f}  faces={p.face_count}  "
            f"sharp={p.sharpness:.3f}  quality={p.quality:.3f}"
        )


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[1]
    default_dir = root / "resource" / "video" / "wedding_web"
    video_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else next(default_dir.glob("wedding_*.mp4"))
    mp_flag = "--mediapipe" in sys.argv
    _demo(video_arg, use_mediapipe=mp_flag)
