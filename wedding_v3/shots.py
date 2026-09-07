"""Shot database: technical + emotion + role metadata with disk cache."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from wedding_v3.emotion import analyze_video, ensure_yunet_model

CACHE_DIR = Path(__file__).resolve().parents[1] / "Output" / "v3_cache" / "shots"
# Bump when emotion/intimacy/color feature schema changes so stale pools are not reused.
CACHE_SCHEMA = "v4_color_continuity"

ROLE_HINTS = {
    "detail": ("5223", "18204", "5183", "5218"),
    "portrait": ("40597", "40591"),
    "couple": ("40596", "40599", "40601", "5206"),
    "motion": ("36171",),
    "wide": ("4829", "5213"),
}


@dataclass
class Shot:
    id: str
    video: str
    start: float
    end: float
    duration: float
    technical_quality: float = 0.0
    cinematic_quality: float = 0.0
    emotion_score: float = 0.0
    emotional_peak_score: float = 0.0
    subjects: list[str] = field(default_factory=list)
    faces: int = 0
    person_ids: list[str] = field(default_factory=list)
    semantic_tags: list[str] = field(default_factory=list)
    shot_type: str = "unknown"
    camera_motion: str = "static"
    composition: str = "centered"
    story_roles: list[str] = field(default_factory=list)
    music_fit: float = 0.0
    novelty: float = 0.5
    best_t: float = 0.0
    smile: float = 0.0
    sharpness: float = 0.0
    kiss: float = 0.0
    hug: float = 0.0
    reaction: float = 0.0
    tears: float = 0.0
    # Mean LAB + HSV saturation at best_t (color continuity / stock-footage fix).
    color_l: float = 50.0
    color_a: float = 0.0
    color_b: float = 0.0
    color_sat: float = 0.35

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Shot":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        return cls(**{k: v for k, v in d.items() if k in known})


def _hint_roles(name: str) -> list[str]:
    stem = Path(name).stem
    roles = []
    for role, keys in ROLE_HINTS.items():
        if any(k in stem for k in keys):
            roles.append(role)
    return roles or ["couple"]


def _sample_color(path: Path, t: float) -> tuple[float, float, float, float]:
    """Return mean (L, a, b, sat01) near timestamp t. Defaults if unreadable."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return 50.0, 0.0, 0.0, 0.35
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_i = max(0, int(float(t) * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_i)
    ok, frame = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_i - int(fps)))
        ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return 50.0, 0.0, 0.0, 0.35
    small = cv2.resize(frame, (160, 90))
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).astype(np.float32)
    # OpenCV LAB: L 0-255, a/b 0-255 centered ~128
    L = float(np.mean(lab[:, :, 0]) * (100.0 / 255.0))
    a = float(np.mean(lab[:, :, 1]) - 128.0)
    b = float(np.mean(lab[:, :, 2]) - 128.0)
    sat = float(np.mean(hsv[:, :, 1]) / 255.0)
    return round(L, 3), round(a, 3), round(b, 3), round(sat, 4)


def color_distance(a: Shot, b: Shot) -> float:
    """Perceptual-ish LAB distance normalized to ~0..1+."""
    dL = float(a.color_l) - float(b.color_l)
    da = float(a.color_a) - float(b.color_a)
    db = float(a.color_b) - float(b.color_b)
    ds = (float(a.color_sat) - float(b.color_sat)) * 40.0
    return float(np.sqrt(dL * dL + da * da + db * db + ds * ds) / 40.0)


def _probe_motion(path: Path, sample_fps: float = 2.0) -> str:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return "static"
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(fps / sample_fps))
    prev = None
    diffs = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            small = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev is not None:
                diffs.append(float(np.mean(cv2.absdiff(gray, prev))))
            prev = gray
        i += 1
    cap.release()
    if not diffs:
        return "static"
    m = float(np.mean(diffs))
    if m > 18:
        return "high"
    if m > 8:
        return "medium"
    return "static"


def _split_windows(duration: float, win: float = 2.2, hop: float = 1.1) -> list[tuple[float, float]]:
    if duration <= win + 0.2:
        return [(0.05, max(0.4, duration - 0.05))]
    out = []
    t = 0.05
    while t + win < duration - 0.05:
        out.append((t, t + win))
        t += hop
    if not out or out[-1][1] < duration - 0.3:
        out.append((max(0.05, duration - win), duration - 0.05))
    return out


def analyze_video_shots(video_path: Path, force: bool = False) -> list[Shot]:
    video_path = Path(video_path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(
        f"{CACHE_SCHEMA}:{video_path.resolve()}:{video_path.stat().st_mtime}".encode()
    ).hexdigest()[:16]
    cache = CACHE_DIR / f"{video_path.stem}_{key}.json"
    if cache.exists() and not force:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return [Shot.from_dict(x) for x in data]

    ensure_yunet_model()
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    nframes = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = float(nframes / fps) if nframes else 8.0
    cap.release()

    moments = analyze_video(str(video_path), sample_fps=2.0)
    motion = _probe_motion(video_path)
    roles = _hint_roles(video_path.name)

    # Global peaks for emotional_peak_score normalization
    emo_vals = [m.emotion_score for m in moments] or [0.0]
    emo_max = max(emo_vals) or 1.0

    shots: list[Shot] = []
    for i, (start, end) in enumerate(_split_windows(duration)):
        mid = (start + end) / 2
        # moments inside window
        inside = [m for m in moments if start <= m.t <= end]
        if not inside and moments:
            inside = [min(moments, key=lambda m: abs(m.t - mid))]
        if not inside:
            continue
        best = max(inside, key=lambda m: m.emotion_score)
        tech = float(np.mean([m.quality for m in inside]))
        emo = float(np.mean([m.emotion_score for m in inside]))
        peak = float(best.emotion_score / emo_max)
        faces = int(max(m.face_count for m in inside))
        smile = float(best.smile)
        kiss = float(max(getattr(m, "kiss", 0.0) for m in inside))
        hug = float(max(getattr(m, "hug", 0.0) for m in inside))
        reaction = float(max(getattr(m, "reaction", 0.0) for m in inside))
        tears = float(max(getattr(m, "tears", 0.0) for m in inside))

        # shot type
        if faces == 0:
            stype = "detail" if "detail" in roles else "wide"
        elif faces >= 2:
            stype = "couple"
        else:
            stype = "portrait"

        story = list(dict.fromkeys(roles + [stype]))
        tags = list(story)
        if smile > 0.35:
            tags.append("smile")
        if kiss >= 0.40:
            tags.append("kiss")
        if hug >= 0.50:
            tags.append("hug")
        if tears >= 0.42:
            tags.append("tears")
        if reaction >= 0.50 and faces >= 1:
            tags.append("reaction")
        if peak > 0.75:
            tags.append("emotional_peak")
        if motion in ("medium", "high"):
            tags.append("movement")

        cinematic = 0.35 * tech + 0.35 * emo + 0.15 * (1.0 if stype in ("portrait", "couple") else 0.5) + 0.15 * (0.7 if motion != "high" else 0.4)

        c_l, c_a, c_b, c_sat = _sample_color(video_path, float(best.t))

        shot = Shot(
            id=f"{video_path.stem}_{i:03d}",
            video=str(video_path).replace("\\", "/"),
            start=round(start, 3),
            end=round(end, 3),
            duration=round(end - start, 3),
            technical_quality=round(tech, 4),
            cinematic_quality=round(cinematic, 4),
            emotion_score=round(emo, 4),
            emotional_peak_score=round(peak, 4),
            subjects=["person"] if faces else ["object"],
            faces=faces,
            semantic_tags=tags,
            shot_type=stype,
            camera_motion=motion,
            composition="close" if faces else "detail",
            story_roles=story,
            novelty=0.5,
            best_t=round(best.t, 3),
            smile=round(smile, 4),
            sharpness=round(best.sharpness, 4),
            kiss=round(kiss, 4),
            hug=round(hug, 4),
            reaction=round(reaction, 4),
            tears=round(tears, 4),
            color_l=c_l,
            color_a=c_a,
            color_b=c_b,
            color_sat=c_sat,
        )
        shots.append(shot)

    cache.write_text(json.dumps([s.to_dict() for s in shots], indent=2), encoding="utf-8")
    return shots


def build_pool(video_dir: Path, force: bool = False) -> list[Shot]:
    video_dir = Path(video_dir)
    all_shots: list[Shot] = []
    videos = sorted(video_dir.glob("*.mp4"))
    for i, vp in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] analyzing {vp.name}", flush=True)
        shots = analyze_video_shots(vp, force=force)
        print(f"  -> {len(shots)} shots, peak emo={max((s.emotion_score for s in shots), default=0):.3f}", flush=True)
        all_shots.extend(shots)
    # novelty: penalize near-duplicate starts from same video later in ranking
    pool_path = CACHE_DIR / "pool.json"
    pool_path.write_text(json.dumps([s.to_dict() for s in all_shots], indent=2), encoding="utf-8")
    print(f"Shot pool: {len(all_shots)} -> {pool_path}", flush=True)
    return all_shots


def load_pool(path: Path | None = None) -> list[Shot]:
    path = path or (CACHE_DIR / "pool.json")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Shot.from_dict(x) for x in data]


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    build_pool(root / "resource" / "video" / "wedding_web")
