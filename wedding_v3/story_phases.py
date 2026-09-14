"""Wedding-day story phases: before / during / after (+ intro/outro).

Gated by craft ``story_phases`` or env WEDDING_V3_STORY_PHASES.
Default off — V2/V3 short films unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from wedding_v3.shots import Shot

STORY_PHASES = os.environ.get("WEDDING_V3_STORY_PHASES", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Default chronological role grammar for a wedding day highlight.
PHASE_ROLE_ARC: dict[str, list[str]] = {
    "intro": ["wide", "detail", "wide"],
    "before": ["detail", "portrait", "detail", "wide", "portrait"],
    "during": ["portrait", "couple", "detail", "couple", "portrait", "couple"],
    "after": ["couple", "motion", "portrait", "couple", "wide"],
    "outro": ["wide", "couple", "detail", "wide"],
}

# Time fractions of the film (exclusive end).
DEFAULT_PHASE_SPINE: list[tuple[str, float, float]] = [
    ("intro", 0.00, 0.06),
    ("before", 0.06, 0.28),
    ("during", 0.28, 0.62),
    ("after", 0.62, 0.90),
    ("outro", 0.90, 1.01),
]


def story_phases_enabled(craft: dict[str, Any] | None = None) -> bool:
    craft = craft or {}
    return bool(craft.get("story_phases")) or STORY_PHASES


def phase_at_time(t: float, duration: float, craft: dict[str, Any] | None = None) -> str:
    """Map absolute time → day phase."""
    craft = craft or {}
    if duration <= 0:
        return "during"
    frac = max(0.0, min(1.0, float(t) / float(duration)))
    spine = craft.get("phase_spine") or DEFAULT_PHASE_SPINE
    for name, a, b in spine:
        if a <= frac < b:
            return str(name)
    return "outro"


def phase_role_prefs(phase: str, craft: dict[str, Any] | None = None) -> list[str]:
    craft = craft or {}
    custom = craft.get("phase_role_arc") or {}
    if phase in custom:
        return list(custom[phase])
    return list(PHASE_ROLE_ARC.get(phase) or PHASE_ROLE_ARC["during"])


def soft_xfade_phases(craft: dict[str, Any] | None = None) -> set[str]:
    craft = craft or {}
    raw = craft.get("soft_xfade_phases")
    if raw:
        return {str(x) for x in raw}
    return {"intro", "before", "outro"}


def hard_cut_phases(craft: dict[str, Any] | None = None) -> set[str]:
    craft = craft or {}
    raw = craft.get("hard_cut_phases")
    if raw:
        return {str(x) for x in raw}
    return {"during", "after"}


def phase_fit(shot: Shot, phase: str) -> float:
    """0..1 how well a shot belongs in a wedding-day phase."""
    role = (shot.shot_type or "").lower()
    tags = {str(t).lower() for t in (shot.semantic_tags or [])}
    kiss = float(shot.kiss or 0)
    hug = float(shot.hug or 0)
    smile = float(shot.smile or 0)
    emo = float(shot.emotion_score or 0)
    name = Path(shot.video).name.lower()
    is_ww = name.startswith("wedding_")
    score = 0.35

    if phase == "intro":
        if role in ("wide", "detail"):
            score += 0.35
        if role == "couple" and kiss >= 0.4:
            score -= 0.25  # no climax in open
        if "wide" in tags or "detail" in tags:
            score += 0.1
    elif phase == "before":
        if role in ("detail", "portrait", "wide"):
            score += 0.30
        if role == "detail":
            score += 0.15
        if kiss >= 0.55:
            score -= 0.20
        if is_ww and role in ("detail", "portrait"):
            score += 0.20
        if smile >= 0.35 and role == "portrait":
            score += 0.12
    elif phase == "during":
        if role in ("couple", "portrait"):
            score += 0.28
        if kiss >= 0.40 or hug >= 0.45:
            score += 0.35
        if role == "detail" and ("detail" in tags or kiss < 0.2):
            score += 0.12  # rings
        if is_ww:
            score += 0.15
        if emo >= 0.55:
            score += 0.10
    elif phase == "after":
        if role in ("couple", "motion", "portrait"):
            score += 0.28
        if smile >= 0.35:
            score += 0.18
        if role == "motion":
            score += 0.15
        if kiss >= 0.7:
            score -= 0.08  # keep true climax in during when possible
    elif phase == "outro":
        if role in ("wide", "couple", "detail"):
            score += 0.32
        if role == "wide":
            score += 0.15
        if kiss >= 0.55:
            score -= 0.10

    return max(0.0, min(1.0, score))
