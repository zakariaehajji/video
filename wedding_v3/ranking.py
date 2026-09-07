"""Shot ranking with experimentable weight profiles."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

from wedding_v3.shots import Shot, color_distance
from wedding_v3.story import PlannedBeat

# V9 experiment gate: prefer sharper / higher cinematic shots to lift visual_quality.
VISUAL_BOOST = os.environ.get("WEDDING_V3_VISUAL_BOOST", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# V10: prefer palette-similar cuts across sources (reduces stock-footage jumps).
COLOR_CONTINUITY = os.environ.get("WEDDING_V3_COLOR_CONTINUITY", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)

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


def _effective_weights(profile: str) -> dict[str, float]:
    """Return ranking weights; optional VISUAL_BOOST / COLOR_CONTINUITY shifts."""
    w = dict(WEIGHT_PROFILES[profile])
    if VISUAL_BOOST:
        # Lift visual preference without starving variety (V9v1 over-cut variety→6.36).
        w["visual"] = min(0.24, w["visual"] + 0.07)
        w["variety"] = max(0.06, w["variety"] - 0.01)
        w["continuity"] = max(0.07, w["continuity"] - 0.01)
    if COLOR_CONTINUITY:
        # More mass on continuity; do not starve emotion/story (V8 strengths).
        w["continuity"] = min(0.16, w["continuity"] + 0.05)
        w["variety"] = max(0.05, w["variety"] - 0.01)
        w["visual"] = max(0.12, w["visual"] - 0.02)
    if VISUAL_BOOST or COLOR_CONTINUITY:
        total = sum(w.values())
        if total > 0:
            w = {k: v / total for k, v in w.items()}
    return w


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
    recent_shots: Sequence[Shot] | None = None,
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
    sharpness = float(getattr(shot, "sharpness", 0.0) or 0.0)
    if VISUAL_BOOST:
        # Critic visual_quality = mean(cinematic_quality); weight CQ + sharpness harder.
        visual = (
            0.35 * shot.technical_quality
            + 0.45 * shot.cinematic_quality
            + 0.20 * sharpness
        )
    else:
        visual = 0.6 * shot.technical_quality + 0.4 * shot.cinematic_quality

    # continuity: prefer same couple/portrait chain, avoid random jumps to detail mid-peak
    continuity = 0.7
    if recent_videos:
        if shot.video in recent_videos[-1:]:
            # V9v2: harder consecutive-source penalty (V9v1 hit "same source repeated").
            continuity = 0.18 if VISUAL_BOOST else 0.35
            reasons.append("same-video-penalty")
        elif shot.shot_type == beat.role:
            continuity = 0.85

    # V10: color match to previous pick across different sources (stock-footage fix).
    if COLOR_CONTINUITY and recent_shots:
        prev = recent_shots[-1]
        dist = color_distance(shot, prev)
        # Smooth map: dist 0 → 1.0, dist 0.5 → ~0.45, dist 1+ → floor
        color_fit = max(0.12, 1.0 - min(1.15, dist * 1.35))
        if shot.video in recent_videos[-1:]:
            # Still punish consecutive same source, but mild color can't override it.
            continuity = min(continuity, 0.22 + 0.15 * color_fit)
        else:
            # Blend role continuity with palette similarity.
            continuity = 0.35 * continuity + 0.65 * color_fit
            if color_fit >= 0.72:
                reasons.append("color-match")
            elif color_fit <= 0.35:
                reasons.append("color-jump")
                continuity *= 0.85

    variety = 1.0
    if shot.id in recent_ids:
        variety = 0.0
        reasons.append("exact-reuse")
    elif shot.video in recent_videos[-3:]:
        variety = 0.30 if VISUAL_BOOST else (0.40 if COLOR_CONTINUITY else 0.45)
        reasons.append("recent-video")
    elif VISUAL_BOOST and recent_videos.count(shot.video) >= 2:
        variety = 0.55
        reasons.append("source-overuse")
    elif COLOR_CONTINUITY and recent_videos.count(shot.video) >= 2:
        variety = 0.50
        reasons.append("source-overuse")

    # peak payoff boost
    if beat.is_peak and shot.smile > 0.35 and shot.faces >= 1:
        peak = min(1.0, peak + 0.25)
        reasons.append("smile-on-peak")
    # Real intimacy > smile-only heuristic for peak / couple moments.
    kiss = float(getattr(shot, "kiss", 0.0) or 0.0)
    hug = float(getattr(shot, "hug", 0.0) or 0.0)
    reaction = float(getattr(shot, "reaction", 0.0) or 0.0)
    tears = float(getattr(shot, "tears", 0.0) or 0.0)
    intimacy = max(kiss, hug * 0.9)
    if beat.is_peak and kiss >= 0.40:
        peak = min(1.0, peak + 0.40)
        emotion = min(1.0, emotion + 0.16)
        reasons.append("kiss-on-peak")
    elif beat.is_peak and hug >= 0.50:
        peak = min(1.0, peak + 0.28)
        emotion = min(1.0, emotion + 0.12)
        reasons.append("hug-on-peak")
    elif beat.is_peak and tears >= 0.42:
        peak = min(1.0, peak + 0.32)
        emotion = min(1.0, emotion + 0.14)
        reasons.append("tears-on-peak")
    elif beat.is_peak and intimacy >= 0.30:
        peak = min(1.0, peak + 0.12)
        emotion = min(1.0, emotion + 0.06)
        reasons.append("near-intimacy-peak")
    if beat.role in ("couple", "portrait") and (kiss >= 0.35 or hug >= 0.45):
        story = min(1.0, story + 0.15)
        reasons.append("intimacy-role-fit")
    if beat.role in ("portrait", "detail") and tears >= 0.40:
        story = min(1.0, story + 0.12)
        emotion = min(1.0, emotion + 0.08)
        reasons.append("tears-role-fit")
    if beat.section in ("chorus", "peak", "outro") and reaction >= 0.50 and shot.faces >= 1:
        emotion = min(1.0, emotion + 0.10)
        reasons.append("reaction-cutaway")
    if beat.section in ("chorus", "peak", "bridge", "outro") and tears >= 0.45:
        emotion = min(1.0, emotion + 0.12)
        peak = min(1.0, peak + 0.10)
        reasons.append("tear-reaction")

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
    # Reserve strong kiss/hug for peaks — burning them on intro/build wastes wedding feeling.
    if intimacy >= 0.40 and not beat.is_peak and beat.section in ("intro", "build", "verse"):
        total *= 0.82
        reasons.append("intimacy-reserved")
    # Soft-reserve strong tear close-ups for emotional sections.
    if tears >= 0.48 and beat.section in ("intro", "build") and not beat.is_peak:
        total *= 0.88
        reasons.append("tears-reserved")
    # Critic hard-penalizes any peak with emotion_score < 0.35 (music_sync *= 0.85).
    if beat.is_peak and shot.emotion_score < 0.35:
        total *= 0.55
        reasons.append("weak-peak-emotion")
    # V9: soft quality floors / boosts so montage mean cinematic_quality rises.
    if VISUAL_BOOST:
        cq = float(shot.cinematic_quality or 0.0)
        tq = float(shot.technical_quality or 0.0)
        if cq < 0.50:
            total *= 0.80
            reasons.append("low-cinematic-floor")
        elif cq >= 0.62:
            total *= 1.08
            reasons.append("high-cinematic-boost")
        if tq < 0.58:
            total *= 0.90
            reasons.append("low-tech-floor")
        elif tq >= 0.78 and sharpness >= 0.85:
            total *= 1.05
            reasons.append("sharp-tech-boost")
        # Intro/outro bookends benefit most from clean frames (stock-footage feel).
        if beat.section in ("intro", "outro") and cq < 0.53:
            total *= 0.88
            reasons.append("bookend-quality")
    # V10: mild warmth preference (wedding film look) without hard filtering.
    if COLOR_CONTINUITY:
        warmth = float(getattr(shot, "color_b", 0.0) or 0.0)  # +b = yellow/warm
        if warmth < -4.0:
            total *= 0.94
            reasons.append("cool-palette")
        elif warmth >= 6.0:
            total *= 1.03
            reasons.append("warm-palette")
        if beat.section in ("intro", "outro"):
            # Bookends: avoid extreme brightness jumps vs film mid-tones.
            L = float(getattr(shot, "color_l", 50.0) or 50.0)
            if L < 28.0 or L > 78.0:
                total *= 0.90
                reasons.append("bookend-exposure")
    if story >= 0.99:
        reasons.append(f"role:{beat.role}")
    return float(total), reasons


def allocate(
    beats: list[PlannedBeat],
    shots: list[Shot],
    profile: str = "C_peak_payoff",
) -> list[RankedPick]:
    weights = _effective_weights(profile)
    picks: list[RankedPick] = []
    recent_videos: list[str] = []
    recent_ids: list[str] = []
    recent_shots: list[Shot] = []
    used_ids: set[str] = set()

    for beat in beats:
        best: RankedPick | None = None
        candidates = shots
        # Prefer unused
        unused = [s for s in shots if s.id not in used_ids]
        if unused:
            candidates = unused
        # V9v2: do NOT hard-filter the pool (V9v1 filtered top-55% CQ → source repeats).
        # Soft floors/boosts in score_shot already prefer high-CQ shots.
        scored = []
        for s in candidates:
            # duration feasibility
            if s.duration + 0.05 < min(0.7, beat.dur * 0.6):
                continue
            sc, reasons = score_shot(
                s, beat, weights, recent_videos, recent_ids, recent_shots
            )
            scored.append((sc, s, reasons))
        if not scored:
            # fallback any
            for s in shots:
                sc, reasons = score_shot(
                    s, beat, weights, recent_videos, recent_ids, recent_shots
                )
                scored.append((sc, s, reasons))
        scored.sort(key=lambda x: x[0], reverse=True)
        sc, s, reasons = scored[0]
        # Center extract around best_t when possible
        pick = RankedPick(beat=beat, shot=s, score=sc, reasons=reasons)
        picks.append(pick)
        used_ids.add(s.id)
        recent_videos.append(s.video)
        recent_ids.append(s.id)
        recent_shots.append(s)
        if len(recent_videos) > 6:
            recent_videos.pop(0)
            recent_ids.pop(0)
            recent_shots.pop(0)
    return picks
