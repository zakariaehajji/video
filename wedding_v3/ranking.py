"""Shot ranking with experimentable weight profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from wedding_v3.shots import Shot
from wedding_v3.story import PlannedBeat

WEIGHT_PROFILES = {
    "A_emotion": {
        "emotion": 0.25,
        "peak": 0.10,
        "story": 0.20,
        "music": 0.15,
        "visual": 0.15,
        "continuity": 0.08,
        "variety": 0.07,
    },
    "B_story_music": {
        "emotion": 0.15,
        "peak": 0.05,
        "story": 0.25,
        "music": 0.25,
        "visual": 0.15,
        "continuity": 0.10,
        "variety": 0.05,
    },
    "C_peak_payoff": {
        "emotion": 0.20,
        "peak": 0.20,
        "story": 0.20,
        "music": 0.15,
        "visual": 0.12,
        "continuity": 0.08,
        "variety": 0.05,
    },
    "D_balanced": {
        "emotion": 0.18,
        "peak": 0.12,
        "story": 0.22,
        "music": 0.18,
        "visual": 0.15,
        "continuity": 0.08,
        "variety": 0.07,
    },
}


@dataclass
class RankedPick:
    beat: PlannedBeat
    shot: Shot
    score: float
    reasons: list[str]


def _role_match(shot: Shot, role: str) -> float:
    if role in shot.story_roles or shot.shot_type == role:
        return 1.0
    # soft adjacency
    adj = {
        "detail": ["portrait"],
        "portrait": ["couple", "detail"],
        "couple": ["portrait", "motion"],
        "motion": ["couple", "wide"],
        "wide": ["detail", "motion"],
    }
    if role in adj and any(r in shot.story_roles or shot.shot_type == r for r in adj[role]):
        return 0.55
    return 0.15


def score_shot(
    shot: Shot,
    beat: PlannedBeat,
    weights: dict[str, float],
    recent_videos: Sequence[str],
    recent_ids: Sequence[str],
) -> tuple[float, list[str]]:
    reasons = []
    emotion = shot.emotion_score
    peak = shot.emotional_peak_score if beat.is_peak else shot.emotional_peak_score * 0.4
    story = _role_match(shot, beat.role)
    # music fit: higher emotion on high energy, calm quality on low energy
    if beat.energy > 0.65:
        music = 0.55 * emotion + 0.45 * (1.0 if shot.camera_motion != "static" else 0.4)
    else:
        music = 0.5 * shot.technical_quality + 0.5 * (1.0 if shot.camera_motion != "high" else 0.35)
    visual = 0.6 * shot.technical_quality + 0.4 * shot.cinematic_quality

    # continuity: prefer same couple/portrait chain, avoid random jumps to detail mid-peak
    continuity = 0.7
    if recent_videos:
        if shot.video in recent_videos[-1:]:
            continuity = 0.35  # same file twice in a row is bad
            reasons.append("same-video-penalty")
        elif shot.shot_type == beat.role:
            continuity = 0.85

    variety = 1.0
    if shot.id in recent_ids:
        variety = 0.0
        reasons.append("exact-reuse")
    elif shot.video in recent_videos[-3:]:
        variety = 0.45
        reasons.append("recent-video")

    # peak payoff boost
    if beat.is_peak and shot.smile > 0.35 and shot.faces >= 1:
        peak = min(1.0, peak + 0.25)
        reasons.append("smile-on-peak")
    # Real intimacy > smile-only heuristic for peak / couple moments.
    kiss = float(getattr(shot, "kiss", 0.0) or 0.0)
    hug = float(getattr(shot, "hug", 0.0) or 0.0)
    reaction = float(getattr(shot, "reaction", 0.0) or 0.0)
    if beat.is_peak and kiss >= 0.40:
        peak = min(1.0, peak + 0.35)
        emotion = min(1.0, emotion + 0.12)
        reasons.append("kiss-on-peak")
    elif beat.is_peak and hug >= 0.50:
        peak = min(1.0, peak + 0.22)
        emotion = min(1.0, emotion + 0.08)
        reasons.append("hug-on-peak")
    if beat.role in ("couple", "portrait") and (kiss >= 0.35 or hug >= 0.45):
        story = min(1.0, story + 0.12)
        reasons.append("intimacy-role-fit")
    if beat.section in ("chorus", "peak", "outro") and reaction >= 0.55 and shot.faces >= 1:
        emotion = min(1.0, emotion + 0.06)
        reasons.append("reaction-cutaway")

    w = weights
    total = (
        w["emotion"] * emotion
        + w["peak"] * peak
        + w["story"] * story
        + w["music"] * music
        + w["visual"] * visual
        + w["continuity"] * continuity
        + w["variety"] * variety
    )
    if story >= 0.99:
        reasons.append(f"role:{beat.role}")
    return float(total), reasons


def allocate(
    beats: list[PlannedBeat],
    shots: list[Shot],
    profile: str = "C_peak_payoff",
) -> list[RankedPick]:
    weights = WEIGHT_PROFILES[profile]
    picks: list[RankedPick] = []
    recent_videos: list[str] = []
    recent_ids: list[str] = []
    used_ids: set[str] = set()

    for beat in beats:
        best: RankedPick | None = None
        candidates = shots
        # Prefer unused
        unused = [s for s in shots if s.id not in used_ids]
        if unused:
            candidates = unused
        scored = []
        for s in candidates:
            # duration feasibility
            if s.duration + 0.05 < min(0.7, beat.dur * 0.6):
                continue
            sc, reasons = score_shot(s, beat, weights, recent_videos, recent_ids)
            scored.append((sc, s, reasons))
        if not scored:
            # fallback any
            for s in shots:
                sc, reasons = score_shot(s, beat, weights, recent_videos, recent_ids)
                scored.append((sc, s, reasons))
        scored.sort(key=lambda x: x[0], reverse=True)
        sc, s, reasons = scored[0]
        # Center extract around best_t when possible
        pick = RankedPick(beat=beat, shot=s, score=sc, reasons=reasons)
        picks.append(pick)
        used_ids.add(s.id)
        recent_videos.append(s.video)
        recent_ids.append(s.id)
        if len(recent_videos) > 6:
            recent_videos.pop(0)
            recent_ids.pop(0)
    return picks
