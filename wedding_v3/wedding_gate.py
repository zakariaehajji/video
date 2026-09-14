"""Wedding-content gate for delivery films (excludes lifestyle stock collage)."""

from __future__ import annotations

import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from wedding_v3.shots import Shot

WEDDING_ONLY = os.environ.get("WEDDING_V3_WEDDING_ONLY", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# landscape | portrait | any — delivery films default landscape (no vertical mix).
ORIENTATION = os.environ.get("WEDDING_V3_ORIENTATION", "any").strip().lower() or "any"

# Optional allow-list of Mixkit IDs from wedding/love category scrapes.
_ALLOWLIST_PATHS = (
    Path(__file__).resolve().parents[1]
    / "Output"
    / "autolab"
    / "highlight_4min"
    / "wedding_mixkit_ids.txt",
    Path(__file__).resolve().parents[1] / "autolab" / "datasets" / "wedding_mixkit_ids.txt",
)
_DENYLIST_PATHS = (
    Path(__file__).resolve().parents[1] / "autolab" / "datasets" / "wedding_mixkit_deny_ids.txt",
)

_NAME_BONUS = (
    "wedding",
    "bride",
    "groom",
    "ceremony",
    "kiss",
    "dress",
    "veil",
    "ring",
    "aisle",
    "vows",
    "bouquet",
)
_NAME_PENALTY = (
    "kitchen",
    "office",
    "laptop",
    "workout",
    "gym",
    "cooking",
    "city_traffic",
    "pool",
    "baby",
    "infant",
    "pregnant",
    "maternity",
    "spaghetti",
    "interview",
    "dishes",
    "boutique",
)

# Hard denylist: Mixkit "wedding" category titles that are lifestyle, not ceremony.
_DENY_IDS = {
    "4841",
    "12165",
    "12160",
    "12153",
    "12155",
    "35973",
    "12162",
    "12168",
    "12157",
    "12158",
    "12159",
    "12154",
    "12156",
    "12161",
    "12163",
    "12164",
    "12166",
    "12167",
    # audited lifestyle leaks from highlight_4min_v10_web frame pass
    "36162",  # studio interview
    "8747",  # kitchen dishes
    "5223",  # sunset lifestyle + dog
    "51221",  # bridal boutique shopping (not wedding day)
}


def _load_allowlist() -> set[str]:
    for p in _ALLOWLIST_PATHS:
        if p.exists():
            return {
                ln.strip()
                for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            }
    return set()


def _load_denylist() -> set[str]:
    ids = set(_DENY_IDS)
    for p in _DENYLIST_PATHS:
        if p.exists():
            ids |= {
                ln.strip()
                for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            }
    return ids


def _mixkit_id(shot: Shot) -> str | None:
    name = Path(shot.video).name
    m = re.search(r"(?:mixkit_|wedding_)(\d+)", name)
    return m.group(1) if m else None


@lru_cache(maxsize=4096)
def probe_orientation(video: str) -> str:
    """Return 'landscape' | 'portrait' | 'square' | 'unknown'."""
    p = Path(video)
    if not p.exists():
        # try resolve by name under resource/video
        root = Path(__file__).resolve().parents[1] / "resource" / "video"
        hits = list(root.rglob(p.name)) if p.name else []
        if not hits:
            return "unknown"
        p = hits[0]
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        parts = (r.stdout or "").strip().split(",")
        if len(parts) != 2:
            return "unknown"
        w, h = int(float(parts[0])), int(float(parts[1]))
        if h > w * 1.05:
            return "portrait"
        if w > h * 1.05:
            return "landscape"
        return "square"
    except Exception:
        return "unknown"


def filter_orientation(shots: list[Shot], mode: str = "landscape") -> list[Shot]:
    """Keep only sources matching orientation mode."""
    mode = (mode or "any").strip().lower()
    if mode in ("", "any", "all"):
        return shots
    want = "portrait" if mode.startswith("port") else "landscape"
    out: list[Shot] = []
    for s in shots:
        o = probe_orientation(str(s.video))
        if o == want or (want == "landscape" and o == "square"):
            out.append(s)
    return out or shots


def wedding_fit(shot: Shot) -> float:
    """0..~1.6 score: intimacy + faces + name hints. Not a probability."""
    w = 0.0
    w += 0.35 * float(shot.kiss or 0.0)
    w += 0.25 * float(shot.hug or 0.0)
    w += 0.18 * float(shot.tears or 0.0)
    w += 0.12 * float(shot.smile or 0.0)
    w += 0.12 * float(shot.reaction or 0.0)
    w += 0.22 * float(shot.emotion_score or 0.0)
    w += 0.18 * float(shot.emotional_peak_score or 0.0)
    faces = int(shot.faces or 0)
    if faces >= 1:
        w += 0.18
    if faces >= 2:
        w += 0.14
    tags = {str(t).lower() for t in (shot.semantic_tags or [])}
    for t in ("kiss", "hug", "tears", "smile", "emotional_peak", "couple"):
        if t in tags:
            w += 0.06
    name = Path(shot.video).name.lower()
    if any(k in name for k in _NAME_BONUS) or name.startswith("wedding_"):
        w += 0.95
    if name.startswith("wedding_"):
        w += 0.55  # hard prefer curated wedding_web ceremony pack
    if any(k in name for k in _NAME_PENALTY):
        w -= 0.35
    allow = _load_allowlist()
    mid = _mixkit_id(shot)
    if allow and mid and mid in allow:
        w += 0.35
    elif allow and mid and mid not in allow and not name.startswith("wedding_"):
        w -= 0.55
    # Flat no-face B-roll can still help as detail/wide if CQ is strong.
    if faces < 1:
        w *= 0.55
        w += 0.08 * float(shot.cinematic_quality or 0.0)
    return float(w)


def filter_wedding_shots(
    shots: list[Shot],
    *,
    min_fit: float = 0.55,
    keep_top_frac: float = 0.55,
    min_keep: int = 300,
    category_strict: bool | None = None,
) -> list[Shot]:
    """Keep high wedding-fit shots; optionally hard-limit to wedding/love Mixkit IDs."""
    if not shots:
        return shots
    allow = _load_allowlist()
    deny = _load_denylist()
    if category_strict is None:
        category_strict = bool(allow) and WEDDING_ONLY
    pool = shots
    if category_strict and allow:
        kept: list[Shot] = []
        for s in shots:
            name = Path(s.video).name.lower()
            mid = _mixkit_id(s)
            if mid and mid in deny:
                continue
            if name.startswith("wedding_"):
                kept.append(s)
                continue
            if mid and mid in allow and mid not in deny:
                kept.append(s)
        if len(kept) >= 60:
            pool = kept
    else:
        # Soft mode: still drop hard denylist IDs.
        pool = [s for s in shots if (_mixkit_id(s) or "") not in deny]
    scored = sorted(((wedding_fit(s), s) for s in pool), key=lambda x: -x[0])
    n = len(scored)
    keep_n = max(min_keep, int(n * keep_top_frac))
    keep_n = min(n, keep_n)
    floor = scored[min(keep_n - 1, n - 1)][0] if scored else 0.0
    out = [s for fit, s in scored[:keep_n] if fit >= min_fit or fit >= floor]
    for _fit, s in scored:
        if float(s.kiss or 0) >= 0.40 or float(s.hug or 0) >= 0.45:
            if s.id not in {x.id for x in out}:
                out.append(s)
    return out or [s for _, s in scored[:min_keep]]
