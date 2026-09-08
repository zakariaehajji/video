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
# V13: mild CQ preference on top of V10 — no V9 hard floors / variety collapse.
VISUAL_SOFT = os.environ.get("WEDDING_V3_VISUAL_SOFT", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# V18: milder than V13; peak-emotion safe; hard consecutive-source skip.
VISUAL_SOFT_V2 = os.environ.get("WEDDING_V3_VISUAL_SOFT_V2", "0").strip().lower() in (
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
# V11: after allocate, linger on strongest peak-emotion shots (steal from weak peaks).
PEAK_HOLD = os.environ.get("WEDDING_V3_PEAK_HOLD", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# V14: milder peak linger (+0.25s, top-3 only) — no aggressive variance steal.
PEAK_HOLD_SOFT = os.environ.get("WEDDING_V3_PEAK_HOLD_SOFT", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# V12: prefer shots that match music-section story grammar.
MUSIC_SECTION_ROLES = os.environ.get("WEDDING_V3_MUSIC_SECTION_ROLES", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# V16: intercalate true guest/family reaction cutaways after intimacy peaks.
REACTION_CUTAWAYS = os.environ.get("WEDDING_V3_REACTION_CUTAWAYS", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# V17: enforce ceremony arc within peak — vows → rings → kiss → exit.
CEREMONY_NARRATIVE = os.environ.get("WEDDING_V3_CEREMONY_NARRATIVE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Montage-craft heuristics (always on; modest deltas — does not replace weight profiles).
CRAFT_SHOT_HEURISTICS = os.environ.get("WEDDING_V3_CRAFT_SHOTS", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)

# How well a planned role / shot type fits each music section (wedding film grammar).
SECTION_ROLE_FIT: dict[str, dict[str, float]] = {
    "intro": {"detail": 1.0, "wide": 0.95, "portrait": 0.72, "couple": 0.42, "motion": 0.28},
    "build": {"portrait": 1.0, "detail": 0.90, "couple": 0.85, "wide": 0.50, "motion": 0.40},
    "verse": {"couple": 1.0, "portrait": 0.95, "detail": 0.70, "motion": 0.55, "wide": 0.50},
    "chorus": {"couple": 1.0, "motion": 0.95, "portrait": 0.80, "wide": 0.50, "detail": 0.35},
    "peak": {"couple": 1.0, "portrait": 0.95, "motion": 0.52, "wide": 0.38, "detail": 0.28},
    "outro": {"wide": 1.0, "couple": 0.95, "detail": 0.85, "portrait": 0.58, "motion": 0.32},
}

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
    if VISUAL_SOFT_V2 and not VISUAL_BOOST and not VISUAL_SOFT:
        # Milder than V13: tiny CQ nudge; protect emotion/variety budgets.
        w["visual"] = min(0.18, w["visual"] + 0.02)
        w["variety"] = max(0.07, w["variety"])
    elif VISUAL_SOFT and not VISUAL_BOOST:
        # Milder than V9: nudge CQ without starving variety/continuity (V10 strengths).
        w["visual"] = min(0.20, w["visual"] + 0.03)
        w["variety"] = max(0.06, w["variety"])  # do not cut variety budget
    if COLOR_CONTINUITY:
        # More mass on continuity; do not starve emotion/story (V8 strengths).
        w["continuity"] = min(0.16, w["continuity"] + 0.05)
        w["variety"] = max(0.05, w["variety"] - 0.01)
        w["visual"] = max(0.12, w["visual"] - 0.02)
    if MUSIC_SECTION_ROLES:
        # Slightly more story+music mass so section grammar can win close races.
        w["story"] = min(0.28, w["story"] + 0.04)
        w["music"] = min(0.24, w["music"] + 0.04)
        w["variety"] = max(0.05, w["variety"] - 0.02)
        w["visual"] = max(0.12, w["visual"] - 0.02)
    if (
        VISUAL_BOOST
        or VISUAL_SOFT
        or VISUAL_SOFT_V2
        or COLOR_CONTINUITY
        or MUSIC_SECTION_ROLES
    ):
        total = sum(w.values())
        if total > 0:
            w = {k: v / total for k, v in w.items()}
    return w


def _section_role_fit(section: str, role: str) -> float:
    table = SECTION_ROLE_FIT.get(section) or {}
    return float(table.get(role, 0.55))


def _is_true_reaction_cutaway(shot: Shot) -> bool:
    """Guest/family reaction: affective faces, not kiss/hug intimacy frames."""
    reaction = float(getattr(shot, "reaction", 0.0) or 0.0)
    kiss = float(getattr(shot, "kiss", 0.0) or 0.0)
    hug = float(getattr(shot, "hug", 0.0) or 0.0)
    faces = int(getattr(shot, "faces", 0) or 0)
    if faces < 1 or reaction < 0.48:
        return False
    if kiss >= 0.35 or hug >= 0.50:
        return False
    return True


def _is_intimacy_peak_shot(shot: Shot, beat: PlannedBeat | None = None) -> bool:
    """Vow/peak intimacy payoff that should be followed by a reaction cutaway."""
    if beat is not None and not (
        beat.is_peak or beat.section in ("peak", "chorus", "bridge")
    ):
        return False
    # True guest reactions are the *response*, not the intimacy trigger.
    if _is_true_reaction_cutaway(shot):
        return False
    kiss = float(getattr(shot, "kiss", 0.0) or 0.0)
    hug = float(getattr(shot, "hug", 0.0) or 0.0)
    tears = float(getattr(shot, "tears", 0.0) or 0.0)
    emotion = float(getattr(shot, "emotion_score", 0.0) or 0.0)
    if kiss >= 0.40 or hug >= 0.50:
        return True
    # Couple tear climax without guest-reaction profile.
    if tears >= 0.48 and emotion >= 0.52 and shot.shot_type == "couple":
        return True
    return False


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
    elif VISUAL_SOFT_V2:
        # Between baseline and V13: mild CQ tilt without V9 sharpness dominance.
        visual = (
            0.55 * shot.technical_quality
            + 0.32 * shot.cinematic_quality
            + 0.13 * sharpness
        )
    elif VISUAL_SOFT:
        # Soft blend: slightly more CQ/sharpness than baseline, far milder than V9.
        visual = (
            0.50 * shot.technical_quality
            + 0.35 * shot.cinematic_quality
            + 0.15 * sharpness
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
    if REACTION_CUTAWAYS:
        # Prefer true guest/family cutaways (not intimacy frames that also score high).
        true_rx = _is_true_reaction_cutaway(shot)
        if beat.section in ("chorus", "peak", "outro", "verse") and true_rx:
            emotion = min(1.0, emotion + 0.16)
            story = min(1.0, story + 0.08)
            reasons.append("reaction-cutaway")
        if recent_shots and _is_intimacy_peak_shot(recent_shots[-1]) and true_rx:
            emotion = min(1.0, emotion + 0.18)
            peak = min(1.0, peak + 0.10)
            story = min(1.0, story + 0.12)
            reasons.append("reaction-after-intimacy")
        # Soft-penalize burning another couple intimacy frame right after intimacy.
        if (
            recent_shots
            and _is_intimacy_peak_shot(recent_shots[-1])
            and (kiss >= 0.40 or hug >= 0.50)
            and not true_rx
        ):
            total_penalty = True  # applied after total computed below
        else:
            total_penalty = False
    else:
        total_penalty = False
        if beat.section in ("chorus", "peak", "outro") and reaction >= 0.50 and shot.faces >= 1:
            emotion = min(1.0, emotion + 0.10)
            reasons.append("reaction-cutaway")
    if beat.section in ("chorus", "peak", "bridge", "outro") and tears >= 0.45:
        emotion = min(1.0, emotion + 0.12)
        peak = min(1.0, peak + 0.10)
        reasons.append("tear-reaction")

    # Craft curriculum: prefer sharp faces, clean exposure, stable intimate framing.
    if CRAFT_SHOT_HEURISTICS:
        tq = float(getattr(shot, "technical_quality", 0.0) or 0.0)
        if beat.role in ("portrait", "couple") and shot.faces >= 1 and sharpness >= 0.70:
            emotion = min(1.0, emotion + 0.07)
            visual = min(1.0, visual + 0.05)
            reasons.append("craft-sharp-face")
        if beat.is_peak and shot.faces < 1:
            # V17: ring-exchange details are intentional on peak — soften penalty.
            if CEREMONY_NARRATIVE and (
                beat.role == "detail" or shot.shot_type == "detail"
            ):
                peak *= 0.94
                emotion *= 0.96
                reasons.append("ceremony-ring-detail")
            else:
                peak *= 0.82
                emotion *= 0.90
                reasons.append("craft-peak-no-face")
        if beat.is_peak and sharpness < 0.45:
            peak *= 0.88
            reasons.append("craft-peak-soft")
        if beat.section in ("intro", "outro") and tq >= 0.75 and shot.camera_motion == "static":
            visual = min(1.0, visual + 0.04)
            reasons.append("craft-stable-bookend")
        if beat.role == "detail" and shot.faces == 0 and tq >= 0.70:
            story = min(1.0, story + 0.06)
            reasons.append("craft-clean-detail")

    # V12: music-section ↔ story-role / shot-type grammar (selection bias, modest deltas).
    if MUSIC_SECTION_ROLES:
        role_fit = _section_role_fit(beat.section, beat.role)
        shot_fit = _section_role_fit(beat.section, shot.shot_type)
        combined = 0.55 * role_fit + 0.45 * shot_fit
        story = min(1.0, 0.62 * story + 0.38 * combined)
        if combined >= 0.90 and (
            beat.role in shot.story_roles or shot.shot_type == beat.role
        ):
            music = min(1.0, music + 0.10)
            reasons.append("section-role-fit")
        elif combined <= 0.40:
            music *= 0.90
            reasons.append("section-role-mismatch")
        # Climax: couple/portrait with real emotion beats weak motion fillers.
        if beat.section == "peak" or beat.is_peak:
            if shot.shot_type in ("couple", "portrait") and emotion >= 0.42:
                music = min(1.0, music + 0.10)
                peak = min(1.0, peak + 0.06)
                reasons.append("peak-emotion-role")
            if beat.role == "motion" and emotion < 0.45:
                music *= 0.86
                reasons.append("weak-peak-motion")
        # Soft establish on intro/outro bookends.
        if beat.section == "intro" and shot.shot_type in ("detail", "wide"):
            music = min(1.0, music + 0.06)
            reasons.append("intro-establish")
        if beat.section == "outro" and shot.shot_type in ("wide", "couple", "detail"):
            music = min(1.0, music + 0.05)
            reasons.append("outro-resolve")

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
    if REACTION_CUTAWAYS and total_penalty:
        total *= 0.88
        reasons.append("intimacy-stack-penalty")
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
    # V13: gentler CQ nudge — tie-breaker only; never collapses source variety.
    elif VISUAL_SOFT:
        cq = float(shot.cinematic_quality or 0.0)
        tq = float(shot.technical_quality or 0.0)
        if cq < 0.48:
            total *= 0.94
            reasons.append("soft-low-cq")
        elif cq >= 0.66:
            total *= 1.035
            reasons.append("soft-high-cq")
        if tq >= 0.80 and sharpness >= 0.88:
            total *= 1.02
            reasons.append("soft-sharp-tech")
        if beat.section in ("intro", "outro") and cq < 0.50:
            total *= 0.95
            reasons.append("soft-bookend-cq")
        # Extra same-source guard when soft CQ would otherwise re-pick one sharp clip.
        if recent_videos and shot.video in recent_videos[-1:]:
            total *= 0.88
            reasons.append("soft-consec-guard")
    # V18: peak-safe soft CQ — lift bookends/verse visual; do not demote peak emotion.
    elif VISUAL_SOFT_V2:
        cq = float(shot.cinematic_quality or 0.0)
        tq = float(shot.technical_quality or 0.0)
        peak_protect = bool(beat.is_peak) and (
            float(shot.emotion_score or 0.0) >= 0.42
            or float(getattr(shot, "kiss", 0.0) or 0.0) >= 0.38
            or float(getattr(shot, "hug", 0.0) or 0.0) >= 0.48
            or float(getattr(shot, "tears", 0.0) or 0.0) >= 0.45
        )
        if peak_protect:
            # Tiny CQ tie-break only — never punish strong emotional peaks.
            if cq >= 0.68:
                total *= 1.015
                reasons.append("softv2-peak-cq")
        else:
            if cq < 0.46:
                total *= 0.96
                reasons.append("softv2-low-cq")
            elif cq >= 0.68:
                total *= 1.028
                reasons.append("softv2-high-cq")
            if tq >= 0.82 and sharpness >= 0.90:
                total *= 1.015
                reasons.append("softv2-sharp-tech")
            if beat.section in ("intro", "outro", "verse") and cq < 0.52:
                total *= 0.94
                reasons.append("softv2-bookend-cq")
            elif beat.section in ("intro", "outro") and cq >= 0.66:
                total *= 1.02
                reasons.append("softv2-bookend-boost")
        # Harder consecutive-source penalty than V13 soft (V9 failure mode).
        if recent_videos and shot.video in recent_videos[-1:]:
            total *= 0.78
            reasons.append("softv2-consec-guard")
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
        # V18: hard consecutive-source skip when a near-tie alternate exists.
        if (
            VISUAL_SOFT_V2
            and recent_videos
            and s.video == recent_videos[-1]
            and len(scored) > 1
        ):
            alt_sc, alt_s, alt_reasons = scored[1]
            if alt_s.video != s.video and alt_sc >= sc * 0.92:
                sc, s, reasons = alt_sc, alt_s, list(alt_reasons) + ["softv2-hard-consec-skip"]
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
    if PEAK_HOLD_SOFT:
        picks = polish_peak_emotion_holds(
            picks, top_k=3, max_extend=0.25, min_keep=1.00, soft=True
        )
    elif PEAK_HOLD:
        picks = polish_peak_emotion_holds(picks)
    if CEREMONY_NARRATIVE:
        picks = polish_ceremony_narrative(picks, shots)
    if REACTION_CUTAWAYS:
        picks = polish_reaction_cutaways(picks, shots)
    return picks


def _emotion_intensity(shot: Shot) -> float:
    kiss = float(getattr(shot, "kiss", 0.0) or 0.0)
    hug = float(getattr(shot, "hug", 0.0) or 0.0)
    tears = float(getattr(shot, "tears", 0.0) or 0.0)
    reaction = float(getattr(shot, "reaction", 0.0) or 0.0)
    return max(
        float(shot.emotional_peak_score or 0.0),
        float(shot.emotion_score or 0.0),
        kiss,
        hug * 0.95,
        tears,
        reaction * 0.85,
        float(shot.smile or 0.0) * 0.7,
    )


def _ceremony_phase(idx_in_peak: int, n_peak: int) -> str:
    """Map peak-local index → ceremony phase (vows→rings→kiss→exit)."""
    if n_peak <= 1:
        return "kiss"
    frac = idx_in_peak / float(max(1, n_peak - 1))
    if frac <= 0.20:
        return "vow"
    if frac <= 0.38:
        return "ring"
    if frac <= 0.78:
        return "kiss"
    return "exit"


def _ceremony_phase_fit(shot: Shot, phase: str) -> float:
    """How well a shot serves a ceremony narrative phase (0..1+)."""
    kiss = float(getattr(shot, "kiss", 0.0) or 0.0)
    hug = float(getattr(shot, "hug", 0.0) or 0.0)
    tears = float(getattr(shot, "tears", 0.0) or 0.0)
    emotion = float(getattr(shot, "emotion_score", 0.0) or 0.0)
    faces = int(getattr(shot, "faces", 0) or 0)
    st = shot.shot_type or ""
    roles = set(shot.story_roles or [])
    tq = float(getattr(shot, "technical_quality", 0.0) or 0.0)

    if phase == "vow":
        # Solemn portraits / tearful faces — not the kiss climax yet.
        if kiss >= 0.40:
            return 0.15
        score = 0.20
        if st == "portrait" or "portrait" in roles:
            score += 0.35
        if tears >= 0.42:
            score += 0.30
        if faces >= 1 and emotion >= 0.45:
            score += 0.20
        if hug >= 0.55:
            score += 0.08
        return min(1.15, score)

    if phase == "ring":
        # Ring-exchange proxy: clean detail / object close-up, or soft couple.
        if st == "detail" or "detail" in roles or faces == 0:
            return min(1.15, 0.55 + 0.35 * tq + 0.10 * (1.0 if emotion < 0.55 else 0.0))
        if kiss >= 0.40:
            return 0.12
        if st == "portrait" and tears < 0.45:
            return 0.40 + 0.15 * tq
        return 0.18

    if phase == "kiss":
        intimacy = max(kiss, hug * 0.92)
        score = 0.15 + 0.55 * intimacy + 0.20 * emotion
        if st == "couple" or "couple" in roles:
            score += 0.15
        if faces >= 2:
            score += 0.08
        if kiss >= 0.40:
            score += 0.18
        return min(1.25, score)

    # exit — resolution: wide / motion / calmer couple after climax
    if kiss >= 0.42:
        return 0.20
    score = 0.20
    if st in ("wide", "motion") or st in roles or "wide" in roles or "motion" in roles:
        score += 0.40
    if st == "couple" and emotion >= 0.40:
        score += 0.22
    if faces == 0 and tq >= 0.65:
        score += 0.15
    return min(1.10, score)


def polish_ceremony_narrative(
    picks: list[RankedPick],
    shots: list[Shot],
    max_swaps: int = 6,
) -> list[RankedPick]:
    """Reorder peak content into vows → rings → kiss → exit ceremony grammar.

    Keeps beat timeline; swaps source shots so early peak = solemn vows,
    mid = ring/detail beat, climax window = strongest kiss/hug, late = exit/wide.
    """
    if len(picks) < 8 or max_swaps < 1:
        return picks

    peak_idxs = [
        i
        for i, p in enumerate(picks)
        if p.beat.is_peak or p.beat.section == "peak"
    ]
    if len(peak_idxs) < 6:
        return picks

    n_peak = len(peak_idxs)
    used = {p.shot.id for p in picks}
    out = list(picks)
    swaps = 0

    # Phase targets: ensure at least one strong match per phase where pool allows.
    phase_slots: dict[str, list[int]] = {"vow": [], "ring": [], "kiss": [], "exit": []}
    for local_i, gi in enumerate(peak_idxs):
        phase_slots[_ceremony_phase(local_i, n_peak)].append(gi)

    def _best_unused(phase: str, avoid_video: str | None) -> Shot | None:
        ranked = sorted(
            shots,
            key=lambda s: _ceremony_phase_fit(s, phase),
            reverse=True,
        )
        for s in ranked:
            if s.id in used:
                continue
            if avoid_video and s.video == avoid_video:
                continue
            # Ring details can be short; others need normal feasibility.
            fit = _ceremony_phase_fit(s, phase)
            if fit < (0.55 if phase == "ring" else 0.62):
                continue
            return s
        return None

    # Priority: kiss climax first (emotional payoff), then vow, exit, ring.
    for phase in ("kiss", "vow", "exit", "ring"):
        slots = phase_slots.get(phase) or []
        if not slots:
            continue
        # Kiss: place top 2 intimacy shots in climax window.
        # Others: ensure at least one good match.
        need = 2 if phase == "kiss" else 1
        placed = 0
        for gi in slots:
            if swaps >= max_swaps or placed >= need:
                break
            cur = out[gi]
            cur_fit = _ceremony_phase_fit(cur.shot, phase)
            # Already good enough — annotate and keep.
            threshold = 0.70 if phase == "kiss" else (0.58 if phase == "ring" else 0.65)
            if cur_fit >= threshold:
                if f"ceremony-{phase}" not in cur.reasons:
                    cur.reasons = list(cur.reasons) + [f"ceremony-{phase}"]
                placed += 1
                continue
            # Don't displace a better kiss if we're filling a non-kiss phase.
            if phase != "kiss" and float(getattr(cur.shot, "kiss", 0.0) or 0.0) >= 0.40:
                continue
            prev_video = out[gi - 1].shot.video if gi > 0 else None
            cand = _best_unused(phase, prev_video)
            if cand is None:
                continue
            # Only swap if clearly better for this phase.
            if _ceremony_phase_fit(cand, phase) < cur_fit + 0.12:
                continue
            # Kiss phase: never install a weak intimacy stand-in.
            if phase == "kiss" and _ceremony_phase_fit(cand, phase) < 0.70:
                continue
            used.discard(cur.shot.id)
            used.add(cand.id)
            reasons = list(cur.reasons) + [
                f"ceremony-{phase}",
                "ceremony-narrative-swap",
            ]
            # Align beat role lightly with phase for downstream titles/critic.
            new_role = cur.beat.role
            if phase == "ring" and cand.shot_type == "detail":
                new_role = "detail"
            elif phase == "vow" and cand.shot_type == "portrait":
                new_role = "portrait"
            elif phase == "kiss" and cand.shot_type in ("couple", "portrait"):
                new_role = cand.shot_type
            elif phase == "exit" and cand.shot_type in ("wide", "motion"):
                new_role = cand.shot_type
            beat = cur.beat
            if new_role != cur.beat.role:
                beat = PlannedBeat(
                    t0=cur.beat.t0,
                    t1=cur.beat.t1,
                    dur=cur.beat.dur,
                    section=cur.beat.section,
                    role=new_role,
                    energy=cur.beat.energy,
                    want_slowmo=cur.beat.want_slowmo,
                    want_xfade=cur.beat.want_xfade,
                    is_peak=cur.beat.is_peak,
                )
            out[gi] = RankedPick(
                beat=beat,
                shot=cand,
                score=max(cur.score, 0.78),
                reasons=reasons,
            )
            swaps += 1
            placed += 1

    # Soft-penalize annotation: if early peak still holds a strong kiss, mark only
    # (structural swap already preferred kiss into climax window).
    for local_i, gi in enumerate(peak_idxs):
        phase = _ceremony_phase(local_i, n_peak)
        if phase == "vow" and float(getattr(out[gi].shot, "kiss", 0.0) or 0.0) >= 0.40:
            if "ceremony-kiss-early" not in out[gi].reasons:
                out[gi].reasons = list(out[gi].reasons) + ["ceremony-kiss-early"]

    return out


def polish_reaction_cutaways(
    picks: list[RankedPick],
    shots: list[Shot],
    max_swaps: int = 4,
) -> list[RankedPick]:
    """After intimacy peak payoffs, force intercalate guest/family reaction shots.

    Classic wedding grammar: vow/kiss/hug → cut to guest tears/smiles.
    Keeps beat durations/timeline; only swaps the source shot.
    """
    if len(picks) < 4 or max_swaps < 1:
        return picks

    used = {p.shot.id for p in picks}
    pool = [s for s in shots if _is_true_reaction_cutaway(s)]
    if not pool:
        return picks

    def _rx_key(s: Shot) -> tuple[float, float, float]:
        # Prefer single-face tearful portraits, then crowd smiles.
        faces = int(getattr(s, "faces", 0) or 0)
        portrait_bonus = 0.12 if s.shot_type == "portrait" or faces == 1 else 0.0
        tears = float(getattr(s, "tears", 0.0) or 0.0)
        reaction = float(getattr(s, "reaction", 0.0) or 0.0)
        return (reaction + portrait_bonus + 0.08 * tears, tears, float(s.emotion_score or 0.0))

    pool_sorted = sorted(pool, key=_rx_key, reverse=True)
    swaps = 0
    out = list(picks)

    for i in range(1, len(out)):
        if swaps >= max_swaps:
            break
        prev = out[i - 1]
        cur = out[i]
        if not _is_intimacy_peak_shot(prev.shot, prev.beat):
            continue
        # Only intercalate on emotional sections (not intro bookends).
        if cur.beat.section not in ("peak", "chorus", "verse", "bridge", "outro"):
            continue
        if _is_true_reaction_cutaway(cur.shot):
            # Already a cutaway — annotate for eval visibility.
            if "reaction-after-intimacy" not in cur.reasons:
                cur.reasons = list(cur.reasons) + ["reaction-after-intimacy"]
            continue
        # Don't displace another strong kiss/hug climax unless we have a strong reaction.
        cur_kiss = float(getattr(cur.shot, "kiss", 0.0) or 0.0)
        if cur_kiss >= 0.42 and swaps >= 2:
            continue

        candidate = None
        for s in pool_sorted:
            if s.id in used:
                continue
            # Duration feasibility vs planned beat.
            if s.duration + 0.05 < min(0.7, cur.beat.dur * 0.6):
                continue
            # Mild consecutive-source guard.
            if s.video == prev.shot.video:
                continue
            candidate = s
            break
        if candidate is None:
            continue

        used.discard(cur.shot.id)
        used.add(candidate.id)
        reasons = list(cur.reasons) + ["reaction-cutaway-forced", "reaction-after-intimacy"]
        out[i] = RankedPick(
            beat=cur.beat,
            shot=candidate,
            score=max(cur.score, 0.75),
            reasons=reasons,
        )
        swaps += 1

    return out


def polish_peak_emotion_holds(
    picks: list[RankedPick],
    top_k: int = 4,
    max_extend: float = 0.70,
    min_keep: float = 0.95,
    soft: bool = False,
) -> list[RankedPick]:
    """Steal duration from weak peak cuts; linger on strongest emotion climaxes.

    Keeps contiguous timeline and total film length (music alignment preserved).
    Creates intentional short-filler / long-climax contrast (wedding pacing).
    soft=True: smaller +0.25s top-k holds, no variance-boost steal.
    """
    n = len(picks)
    if n < 5:
        return picks
    peak_idxs = [i for i, p in enumerate(picks) if p.beat.is_peak or p.beat.section == "peak"]
    if len(peak_idxs) < 2:
        return picks

    ranked = sorted(peak_idxs, key=lambda i: _emotion_intensity(picks[i].shot), reverse=True)
    climaxes = ranked[: min(top_k, max(2, len(peak_idxs) // 3))]
    climax_set = set(climaxes)

    extensions: dict[int, float] = {}
    for i in climaxes:
        cur = float(picks[i].beat.dur)
        avail = float(picks[i].shot.duration)
        if soft:
            # Mild linger only — respect max_extend hard cap (+0.25s typical).
            target = min(avail * 0.92, cur + max_extend)
        else:
            # Linger ~1.85–2.25s on true emotion peaks; respect source length.
            target = min(2.25, max(cur + 0.35, 1.85), avail * 0.92, cur + max_extend)
        if target > cur + (0.05 if soft else 0.08):
            extensions[i] = target - cur
    need = sum(extensions.values())
    if need < (0.08 if soft else 0.12):
        return picks

    # Donors: weakest emotion among non-climax (prefer peak filler over bookends).
    donors = [i for i in range(n) if i not in climax_set and i not in (0, n - 1)]
    donors.sort(key=lambda i: (_emotion_intensity(picks[i].shot), -float(picks[i].beat.dur)))

    shrinks: dict[int, float] = {}
    remaining = need
    max_give = 0.28 if soft else 0.60
    for i in donors:
        if remaining <= 0.02:
            break
        cur = float(picks[i].beat.dur)
        floor = min_keep
        # Never shrink a strong intimacy beat below comfort.
        if _emotion_intensity(picks[i].shot) >= 0.55:
            floor = max(floor, 1.20)
        # Peak-section filler can go shorter to fund climax breathes.
        if picks[i].beat.section == "peak" and _emotion_intensity(picks[i].shot) < 0.52:
            floor = min(floor, 0.95 if soft else 0.90)
        can = max(0.0, cur - floor)
        give = min(can, remaining, max_give)
        if give >= (0.04 if soft else 0.06):
            shrinks[i] = give
            remaining -= give

    gained = need - remaining
    if gained < (0.06 if soft else 0.10):
        return picks
    if remaining > 0.05:
        scale = gained / need
        extensions = {i: e * scale for i, e in extensions.items()}

    # If duration variance would flatten below critic pacing floor (~0.05), steal a
    # little more from weakest mid cuts into the top climax (real short/long contrast).
    # Soft mode skips this — it can exceed the mild +0.25s intent.
    if not soft:
        trial = [
            float(picks[i].beat.dur) + extensions.get(i, 0.0) - shrinks.get(i, 0.0)
            for i in range(n)
        ]
        mean_t = sum(trial) / n
        var_t = sum((d - mean_t) ** 2 for d in trial) / n
        if var_t < 0.055 and climaxes:
            top = climaxes[0]
            extra_donors = sorted(
                [i for i in donors if i not in shrinks and i != top],
                key=lambda i: _emotion_intensity(picks[i].shot),
            )
            bump = 0.0
            for i in extra_donors[:4]:
                cur = trial[i]
                floor = 0.90 if picks[i].beat.section == "peak" else 1.00
                give = min(0.28, max(0.0, cur - floor))
                if give >= 0.08:
                    shrinks[i] = shrinks.get(i, 0.0) + give
                    bump += give
            if bump >= 0.10:
                extensions[top] = extensions.get(top, 0.0) + bump

    hold_tag = "peak-emotion-hold-soft" if soft else "peak-emotion-hold"
    hold_mark = 0.08 if soft else 0.12

    # Rebuild contiguous beats from original start.
    t0 = float(picks[0].beat.t0)
    new_picks: list[RankedPick] = []
    for i, p in enumerate(picks):
        dur = float(p.beat.dur) + extensions.get(i, 0.0) - shrinks.get(i, 0.0)
        dur = max(0.7, round(dur, 3))
        t1 = round(t0 + dur, 3)
        slow = p.beat.want_slowmo
        reasons = list(p.reasons)
        if i in climax_set and extensions.get(i, 0.0) >= hold_mark:
            reasons = reasons + [hold_tag]
            # Soft slowmo on strongest climaxes if couple/portrait (V11 only).
            if (
                not soft
                and p.beat.role in ("couple", "portrait")
                and _emotion_intensity(p.shot) >= 0.55
                and p.shot.emotion_score >= 0.35
            ):
                slow = True
        beat = PlannedBeat(
            t0=round(t0, 3),
            t1=t1,
            dur=round(t1 - t0, 3),
            section=p.beat.section,
            role=p.beat.role,
            energy=p.beat.energy,
            want_slowmo=slow,
            want_xfade=p.beat.want_xfade and not p.beat.is_peak,
            is_peak=p.beat.is_peak,
        )
        new_picks.append(RankedPick(beat=beat, shot=p.shot, score=p.score, reasons=reasons))
        t0 = t1

    # Cap slowmo density (critic penalizes > n//3; V5 sweet spot is 1..n//5).
    cap = max(2, len(new_picks) // 5)
    slow_idxs = [i for i, p in enumerate(new_picks) if p.beat.want_slowmo]
    if len(slow_idxs) > cap:
        # Keep climax slowmos first, then earliest.
        def _slow_keep_key(i: int) -> tuple:
            return (
                0 if i in climax_set else 1,
                -_emotion_intensity(new_picks[i].shot),
                i,
            )

        keep = set(sorted(slow_idxs, key=_slow_keep_key)[:cap])
        trimmed: list[RankedPick] = []
        for i, p in enumerate(new_picks):
            if p.beat.want_slowmo and i not in keep:
                beat = PlannedBeat(
                    t0=p.beat.t0,
                    t1=p.beat.t1,
                    dur=p.beat.dur,
                    section=p.beat.section,
                    role=p.beat.role,
                    energy=p.beat.energy,
                    want_slowmo=False,
                    want_xfade=p.beat.want_xfade,
                    is_peak=p.beat.is_peak,
                )
                trimmed.append(RankedPick(beat=beat, shot=p.shot, score=p.score, reasons=p.reasons))
            else:
                trimmed.append(p)
        new_picks = trimmed
    return new_picks
