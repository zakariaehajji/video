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
    kiss: float = 0.0
    hug: float = 0.0
    reaction: float = 0.0
    tears: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def proximity_intimacy(faces: np.ndarray, frame_shape: tuple[int, ...]) -> tuple[float, float]:
    """Estimate kiss/hug likelihood from multi-face geometry (YuNet boxes).

    kiss: two faces very close (centers near, overlapping / tiny gap).
    hug: two faces close with similar scale (embrace / cheek-to-cheek).
    Pure geometry — no paid APIs.
    """
    if faces is None or len(faces) < 2:
        return 0.0, 0.0
    h, w = frame_shape[:2]
    diag = float(np.hypot(w, h)) or 1.0
    boxes = []
    for face in faces:
        x, y, fw, fh = [float(v) for v in face[:4]]
        if fw <= 1 or fh <= 1:
            continue
        cx, cy = x + fw * 0.5, y + fh * 0.5
        boxes.append((cx, cy, fw, fh, fw * fh))
    if len(boxes) < 2:
        return 0.0, 0.0

    best_kiss = 0.0
    best_hug = 0.0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax, ay, aw, ah, aa = boxes[i]
            bx, by, bw, bh, ba = boxes[j]
            dist = float(np.hypot(ax - bx, ay - by))
            mean_size = 0.5 * (max(aw, ah) + max(bw, bh))
            # Normalized gap: 0 = centers as close as one face-width.
            gap = dist / max(mean_size, 1.0)
            scale_ratio = min(aa, ba) / max(aa, ba, 1.0)
            # Horizontal bias (faces side-by-side) favors hug/kiss over stacked crowd.
            horiz = abs(ax - bx) / max(dist, 1.0)
            vert = abs(ay - by) / max(dist, 1.0)

            kiss = _clip01((1.15 - gap) / 0.55) * _clip01(scale_ratio / 0.55)
            kiss *= _clip01(0.55 + 0.45 * horiz)
            # Extra boost when face boxes nearly touch / overlap.
            if gap < 0.85:
                kiss = _clip01(kiss + 0.25)
            if gap < 0.55:
                kiss = _clip01(kiss + 0.2)

            hug = _clip01((1.55 - gap) / 0.85) * _clip01(scale_ratio / 0.45)
            hug *= _clip01(0.4 + 0.6 * horiz)
            # Mild penalty if faces are tiny in frame (crowd / background).
            size_frac = mean_size / diag
            hug *= _clip01((size_frac - 0.04) / 0.08)
            kiss *= _clip01((size_frac - 0.05) / 0.07)
            # Vertical stack (one above other) is less likely a kiss.
            if vert > 0.75 and horiz < 0.35:
                kiss *= 0.35
                hug *= 0.55

            best_kiss = max(best_kiss, kiss)
            best_hug = max(best_hug, hug)
    return best_kiss, best_hug


def tear_score(
    faces: np.ndarray,
    gray: np.ndarray,
    smile: float,
    quality: float,
) -> float:
    """Estimate tearful / solemn emotion from under-eye sheen + subdued smile.

    Pure local heuristics on YuNet boxes/landmarks — no paid APIs.
    """
    if faces is None or len(faces) < 1 or gray.size == 0:
        return 0.0
    h, w = gray.shape[:2]
    best = 0.0
    for face in faces:
        x, y, fw, fh = [float(v) for v in face[:4]]
        if fw < 18 or fh < 22:
            continue
        xi, yi = int(max(0, x)), int(max(0, y))
        x2, y2 = int(min(w, x + fw)), int(min(h, y + fh))
        if x2 - xi < 16 or y2 - yi < 20:
            continue
        # YuNet: right-eye, left-eye landmarks (image coords).
        re_x, re_y, le_x, le_y = [float(v) for v in face[4:8]]
        eye_cy = 0.5 * (re_y + le_y)
        eye_span = abs(le_x - re_x) / max(fw, 1.0)
        # Under-eye band: just below eyes, above mid-face.
        uy0 = int(np.clip(eye_cy + 0.02 * fh, yi, y2 - 1))
        uy1 = int(np.clip(eye_cy + 0.22 * fh, uy0 + 2, y2))
        ux0 = int(np.clip(min(re_x, le_x) - 0.05 * fw, xi, x2 - 1))
        ux1 = int(np.clip(max(re_x, le_x) + 0.05 * fw, ux0 + 2, x2))
        under = gray[uy0:uy1, ux0:ux1]
        cheek_y0 = int(np.clip(y + 0.55 * fh, yi, y2 - 1))
        cheek_y1 = int(np.clip(y + 0.78 * fh, cheek_y0 + 2, y2))
        cheek = gray[cheek_y0:cheek_y1, xi:x2]
        if under.size < 8 or cheek.size < 8:
            continue
        under_mean = float(np.mean(under))
        cheek_mean = float(np.mean(cheek))
        # Tear sheen: under-eye brighter / glossier than cheek.
        sheen = _clip01((under_mean - cheek_mean) / 28.0)
        under_std = float(np.std(under))
        gloss = _clip01((under_std - 8.0) / 22.0)
        # Solemn / crying faces: present eyes, NOT a big grin.
        solemn = _clip01(0.55 - smile)  # peaks when smile is low-moderate
        eye_presence = _clip01((eye_span - 0.22) / 0.28)
        face_frac = (fw * fh) / float(max(w * h, 1))
        closeup = _clip01((face_frac - 0.03) / 0.10)
        cue = _clip01(
            0.34 * sheen
            + 0.22 * gloss
            + 0.24 * solemn
            + 0.12 * eye_presence
            + 0.08 * closeup
        )
        cue *= _clip01(0.55 + 0.45 * quality)
        # Very high smile is celebration, not tears.
        if smile >= 0.62:
            cue *= 0.25
        best = max(best, cue)
    return _clip01(best)


def reaction_score(
    smile: float,
    face_count: int,
    quality: float,
    kiss: float = 0.0,
    tears: float = 0.0,
) -> float:
    """Guest/reaction cue: smile, crowd, tears — not kiss intimacy frames."""
    if face_count < 1:
        return 0.0
    crowd = _clip01((face_count - 1) / 2.0)
    # Warm guest smile OR tearful solemn reaction both count.
    affective = max(smile, tears * 0.95)
    base = _clip01(0.38 * affective + 0.28 * crowd + 0.18 * quality + 0.16 * tears)
    # Single-face tearful close-up is a classic cutaway.
    if face_count == 1 and tears >= 0.40:
        base = max(base, _clip01(0.55 * tears + 0.25 * quality + 0.10))
    # Kiss frames are intimacy, not cutaway reactions.
    if kiss >= 0.45:
        base *= 0.35
    return _clip01(base)


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
            output_face_blendshapes=True,
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
        """Smile from MediaPipe blendshapes (preferred) + landmark geometry."""
        smile, _solemn = self.affect_mediapipe(frame_bgr)
        return smile

    def affect_mediapipe(self, frame_bgr: np.ndarray) -> tuple[float, float]:
        """Return (smile, solemn) from Face Landmarker blendshapes + geometry.

        Blendshapes give a real expression model beyond YuNet mouth-corner heuristics.
        Solemn cues (frown / brow down / low smile) feed tear/reaction paths.
        """
        if self._landmarker is None:
            return 0.0, 0.0
        import mediapipe as mp

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return 0.0, 0.0

        smile_scores: list[float] = []
        solemn_scores: list[float] = []
        blend_lists = result.face_blendshapes or [None] * len(result.face_landmarks)
        for landmarks, blendshapes in zip(result.face_landmarks, blend_lists):
            # Landmark geometry fallback (mouth corners / lip open).
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
            geom = _clip01(0.5 * width_score + 0.35 * lift_score + 0.15 * open_score)

            bs_smile = 0.0
            bs_solemn = 0.0
            if blendshapes is not None:
                by_name = {b.category_name: float(b.score) for b in blendshapes}
                left_s = by_name.get("mouthSmileLeft", 0.0)
                right_s = by_name.get("mouthSmileRight", 0.0)
                bs_smile = _clip01(0.55 * left_s + 0.45 * right_s)
                frown = 0.5 * (
                    by_name.get("mouthFrownLeft", 0.0) + by_name.get("mouthFrownRight", 0.0)
                )
                brow = 0.5 * (
                    by_name.get("browDownLeft", 0.0) + by_name.get("browDownRight", 0.0)
                )
                brow_inner = by_name.get("browInnerUp", 0.0)
                bs_solemn = _clip01(
                    0.40 * frown + 0.30 * brow + 0.20 * brow_inner + 0.10 * (1.0 - bs_smile)
                )

            if blendshapes is not None:
                smile_scores.append(_clip01(0.62 * bs_smile + 0.38 * geom))
                solemn_scores.append(bs_solemn)
            else:
                smile_scores.append(geom)
                solemn_scores.append(0.0)

        smile = float(max(smile_scores)) if smile_scores else 0.0
        solemn = float(max(solemn_scores)) if solemn_scores else 0.0
        return smile, solemn


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

    mp_solemn = 0.0
    if backend.use_mediapipe and backend._landmarker is not None:
        mp_smile, mp_solemn = backend.affect_mediapipe(frame_bgr)
        # Only blend when MediaPipe actually resolved a face; never crush YuNet with zeros.
        if mp_smile > 0.02 or mp_solemn > 0.05:
            blended = _clip01(0.42 * smile + 0.58 * mp_smile)
            # Prefer the stronger cue so true smiles are not diluted by timid blendshapes.
            smile = max(smile, blended) if smile >= 0.30 else blended

    kiss, hug = proximity_intimacy(faces, frame_bgr.shape)
    tears = tear_score(faces, gray, smile=smile, quality=quality)
    # MediaPipe solemn expression reinforces tear/reaction beyond under-eye sheen alone.
    if mp_solemn >= 0.28:
        tears = _clip01(max(tears, 0.55 * tears + 0.45 * mp_solemn))
    reaction = reaction_score(smile, face_count, quality, kiss=kiss, tears=tears)

    # Favor smiles, intimacy (kiss/hug), tears/reactions, visible faces, usable frames.
    face_presence = _clip01(face_count / 2.0)
    intimacy = max(kiss, hug * 0.85)
    emotion = _clip01(
        0.28 * smile
        + 0.18 * intimacy
        + 0.14 * tears
        + 0.10 * reaction
        + 0.14 * face_presence
        + 0.16 * quality
    )
    # Kiss/hug frames are wedding-critical even if smile heuristic is weak.
    if kiss >= 0.45 or hug >= 0.55:
        emotion = _clip01(max(emotion, 0.55 * emotion + 0.45 * intimacy + 0.08))
    # Tearful / solemn faces are true emotional peaks beyond grin heuristics.
    if tears >= 0.42:
        emotion = _clip01(max(emotion, 0.50 * emotion + 0.42 * tears + 0.10 * quality))

    return FrameMoment(
        t=float(t),
        emotion_score=emotion,
        smile=smile,
        face_count=face_count,
        sharpness=sharp,
        quality=quality,
        kiss=kiss,
        hug=hug,
        reaction=reaction,
        tears=tears,
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
