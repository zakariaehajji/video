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
    if VISUAL_SOFT and not VISUAL_BOOST:
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
    if VISUAL_BOOST or VISUAL_SOFT or COLOR_CONTINUITY or MUSIC_SECTION_ROLES:
        total = sum(w.values())
        if total > 0:
            w = {k: v / total for k, v in w.items()}
    return w


def _section_role_fit(section: str, role: str) -> float:
    table = SECTION_ROLE_FIT.get(section) or {}
    return float(table.get(role, 0.55))


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
    if PEAK_HOLD_SOFT:
        picks = polish_peak_emotion_holds(
            picks, top_k=3, max_extend=0.25, min_keep=1.00, soft=True
        )
    elif PEAK_HOLD:
        picks = polish_peak_emotion_holds(picks)
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
