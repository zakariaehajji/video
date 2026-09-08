"""Adaptive wedding story planning from music sections + available shot roles."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from wedding_v3.music import MusicAnalysis
from wedding_v3.shots import Shot

# V5 experiment gate: set WEDDING_V3_PACE_HOLD=1 to enforce min shot holds.
# Default off so V4_xfade and baseline V3 behavior stay comparable.
PACE_HOLD_FLOOR = os.environ.get("WEDDING_V3_PACE_HOLD", "0").strip() in ("1", "true", "yes")
# V11: linger on musical peak / emotion climaxes (do not shorten peak holds).
PEAK_HOLD = os.environ.get("WEDDING_V3_PEAK_HOLD", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# V12: tighter music-section → story-role grammar (energy-aware role picks).
MUSIC_SECTION_ROLES = os.environ.get("WEDDING_V3_MUSIC_SECTION_ROLES", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)


ARC_BY_SECTION = {
    "intro": ["detail", "wide", "portrait"],
    "build": ["portrait", "detail", "couple"],
    "verse": ["couple", "portrait", "motion"],
    "chorus": ["couple", "motion", "portrait"],
    "peak": ["couple", "portrait", "motion"],
    "outro": ["wide", "couple", "detail"],
}

# Wedding-film grammar: establish → intimacy → celebration → climax → resolve.
# Peak favors couple/portrait; motion is a sparse accent, not equal rotation.
ARC_BY_SECTION_TIGHT = {
    "intro": ["detail", "wide", "detail", "wide", "portrait"],
    "build": ["portrait", "detail", "portrait", "couple"],
    "verse": ["couple", "portrait", "detail", "couple"],
    "chorus": ["couple", "motion", "couple", "portrait"],
    "peak": ["couple", "portrait", "couple", "portrait", "couple", "motion"],
    "outro": ["wide", "couple", "detail", "wide"],
}


def _select_section_role(
    prefs: list[str],
    idx: int,
    energy: float,
    label: str,
) -> str:
    """Pick beat role; V12 biases by section grammar + local energy."""
    if not prefs:
        return "couple"
    if not MUSIC_SECTION_ROLES:
        return prefs[idx % len(prefs)]

    primary = {
        "intro": ["detail", "wide"],
        "build": ["portrait", "detail"],
        "verse": ["couple", "portrait"],
        "chorus": ["couple", "motion"],
        "peak": ["couple", "portrait"],
        "outro": ["wide", "couple"],
    }.get(label, prefs)
    primary = [r for r in primary if r in prefs] or list(prefs)

    if energy >= 0.68:
        ordered = [r for r in ("motion", "couple", "portrait", "wide", "detail") if r in prefs]
    elif energy <= 0.42:
        ordered = [r for r in ("detail", "wide", "portrait", "couple", "motion") if r in prefs]
    else:
        ordered = [r for r in prefs if r in prefs]

    if not ordered:
        ordered = list(prefs)

    # Early beats in a section stick to primary wedding grammar.
    if idx < 2:
        return primary[idx % len(primary)]
    # Peak: keep motion rare (every 6th beat after openers).
    if label == "peak":
        if "motion" in prefs and idx >= 2 and idx % 6 == 5:
            return "motion"
        peak_cycle = [r for r in ("couple", "portrait") if r in prefs] or primary
        return peak_cycle[idx % len(peak_cycle)]
    # Otherwise cycle prefs (tight arc order) with energy-ordered fallback every 4th.
    if idx % 4 == 3 and ordered:
        return ordered[idx % len(ordered)]
    return prefs[idx % len(prefs)]


@dataclass
class PlannedBeat:
    t0: float
    t1: float
    dur: float
    section: str
    role: str
    energy: float
    want_slowmo: bool
    want_xfade: bool
    is_peak: bool


def _section_energy(analysis: MusicAnalysis, start: float, end: float) -> float:
    data = analysis.to_dict()
    curve = data.get("energy_curve") or {}
    times = curve.get("times") or []
    values = curve.get("values") or []
    if not times or not values:
        return 0.5
    vals = [e for t, e in zip(times, values) if start <= t <= end]
    return float(sum(vals) / len(vals)) if vals else 0.5


def plan_story(
    analysis: MusicAnalysis,
    available_roles: set[str],
    target_duration: float = 38.0,
    style: str = "classic",
    craft: dict[str, Any] | None = None,
) -> list[PlannedBeat]:
    """Build adaptive beat list. Skips roles that have no footage.

    Optional ``craft`` (from autolab/craft/templates) overrides role arc + pacing floors.
    """
    global PACE_HOLD_FLOOR, PEAK_HOLD
    craft = craft or {}
    restore_pace = PACE_HOLD_FLOOR
    restore_peak = PEAK_HOLD
    if craft.get("pace_hold"):
        PACE_HOLD_FLOOR = True
    if craft.get("peak_hold"):
        PEAK_HOLD = True
    if craft.get("target_duration"):
        target_duration = float(craft["target_duration"])

    data = analysis.to_dict()
    duration = min(float(data["duration"]), target_duration)
    sections = [s for s in data.get("sections", []) if s["start"] < duration]
    if not sections:
        sections = [{"start": 0.0, "end": duration, "label": "verse", "mean_energy": 0.5}]

    if sections[-1]["end"] > duration:
        sections[-1]["end"] = duration

    beats: list[PlannedBeat] = []
    beat_times = [b for b in data.get("beat_times", []) if b <= duration]
    peak_times = []
    for p in data.get("peaks", []):
        if isinstance(p, dict):
            peak_times.append(float(p.get("time", 0)))
        else:
            peak_times.append(float(p))
    peaks = set(round(p, 1) for p in peak_times)

    craft_arc = craft.get("role_arc") or {}
    craft_min = float(craft.get("min_shot_dur") or 0)
    craft_max = float(craft.get("max_shot_dur") or 99)
    craft_peak_min = float(craft.get("peak_min_dur") or 0)
    craft_xfade = set(craft.get("prefer_xfade_sections") or [])
    craft_hard_peak = bool(craft.get("hard_cut_on_peak", True))

    try:
        for si, sec in enumerate(sections):
            s0, s1 = float(sec["start"]), float(min(sec["end"], duration))
            if s1 - s0 < 0.6:
                continue
            label = sec.get("label", "verse")
            if craft_arc and label in craft_arc:
                arc_prefs = craft_arc[label]
            else:
                arc = ARC_BY_SECTION_TIGHT if MUSIC_SECTION_ROLES else ARC_BY_SECTION
                arc_prefs = arc.get(label, ["couple"])
            prefs = [r for r in arc_prefs if r in available_roles]
            if not prefs:
                prefs = list(available_roles) or ["couple"]

            energy = float(sec.get("mean_energy", _section_energy(analysis, s0, s1)))
            if style == "emotional":
                if PACE_HOLD_FLOOR:
                    base = 2.9 if label in ("intro", "outro") else 2.15
                    min_dur = 1.4 if label in ("intro", "outro", "build") else 1.2
                else:
                    base = 2.85 if label in ("intro", "outro") else 2.05
                    min_dur = 0.7
            elif style == "energetic":
                base = 1.9 if label in ("intro", "outro") else 1.25
                min_dur = 0.85 if PACE_HOLD_FLOOR else 0.7
            else:
                base = 2.6 if label in ("intro", "outro") else 1.9 if label == "build" else 1.55
                min_dur = (1.2 if label in ("intro", "outro") else 1.05) if PACE_HOLD_FLOOR else 0.7

            if craft_min > 0:
                min_dur = max(min_dur, craft_min)
                base = max(base, craft_min)

            if energy > 0.7:
                base *= 0.9
            if label == "peak":
                if PEAK_HOLD and PACE_HOLD_FLOOR:
                    if style == "emotional":
                        base = min(base, 1.62)
                        min_dur = min(min_dur, 1.05)
                    else:
                        base = min(base, 1.40)
                        min_dur = min(min_dur, 0.90)
                elif PACE_HOLD_FLOOR:
                    base = min(base, 1.55 if style == "emotional" else 1.35)
                    min_dur = min(min_dur, 1.0 if style == "emotional" else 0.85)
                else:
                    base = min(base, 1.45 if style == "emotional" else 1.35)
                if craft_peak_min > 0:
                    base = max(base, craft_peak_min)
                    min_dur = max(min_dur, craft_peak_min)

            base = min(base, craft_max)
            min_dur = min(min_dur, craft_max)

            t = s0
            idx = 0
            while t < s1 - 0.45:
                role = _select_section_role(prefs, idx, energy, label)
                dur = base
                if PACE_HOLD_FLOOR:
                    future_beats = [b for b in beat_times if b > t + min_dur]
                    if future_beats:
                        gap = future_beats[0] - t
                        if min_dur <= gap <= max(2.8, base + 0.4):
                            dur = gap
                    dur = max(dur, min_dur)
                else:
                    future_beats = [b for b in beat_times if b > t + 0.5]
                    if future_beats:
                        gap = future_beats[0] - t
                        if 0.7 <= gap <= 2.8:
                            dur = gap
                dur = min(dur, craft_max)
                end = min(s1, t + dur)
                if end - t < (min(0.55, min_dur * 0.55) if PACE_HOLD_FLOOR else 0.55):
                    break
                if PACE_HOLD_FLOOR:
                    rem = s1 - end
                    if 0 < rem < min_dur * 0.75:
                        end = s1

                near_peak = any(abs((t + end) / 2 - p) < 1.2 for p in peaks) or label == "peak"
                is_peak = label == "peak" or (
                    near_peak and label in ("chorus", "verse", "build")
                )
                want_slow = is_peak and role in ("couple", "portrait") and energy > 0.45
                soft = craft_xfade or {"intro", "outro", "build"}
                want_xfade = (
                    label in soft
                    and energy < 0.55
                    and style != "energetic"
                    and not (is_peak and craft_hard_peak)
                )

                beats.append(
                    PlannedBeat(
                        t0=round(t, 3),
                        t1=round(end, 3),
                        dur=round(end - t, 3),
                        section=label,
                        role=role,
                        energy=round(energy, 4),
                        want_slowmo=want_slow,
                        want_xfade=want_xfade,
                        is_peak=is_peak,
                    )
                )
                t = end
                idx += 1

        # Cap peak-slowmo density when pace-hold is on.
        if PACE_HOLD_FLOOR and beats:
            cap = max(2, len(beats) // 5)
            kept = 0
            capped: list[PlannedBeat] = []
            for b in beats:
                slow = b.want_slowmo
                if slow:
                    if b.role != "couple" or kept >= cap:
                        slow = False
                    else:
                        kept += 1
                if slow == b.want_slowmo:
                    capped.append(b)
                else:
                    capped.append(
                        PlannedBeat(
                            t0=b.t0,
                            t1=b.t1,
                            dur=b.dur,
                            section=b.section,
                            role=b.role,
                            energy=b.energy,
                            want_slowmo=slow,
                            want_xfade=b.want_xfade,
                            is_peak=b.is_peak,
                        )
                    )
            beats = capped

        if beats and beats[-1].t1 < duration - 0.4:
            role = (
                "wide"
                if "wide" in available_roles
                else ("couple" if "couple" in available_roles else next(iter(available_roles), "couple"))
            )
            beats.append(
                PlannedBeat(
                    t0=beats[-1].t1,
                    t1=duration,
                    dur=round(duration - beats[-1].t1, 3),
                    section="outro",
                    role=role,
                    energy=0.35,
                    want_slowmo=False,
                    want_xfade=True,
                    is_peak=False,
                )
            )
        return beats
    finally:
        PACE_HOLD_FLOOR = restore_pace
        PEAK_HOLD = restore_peak


def available_roles_from_shots(shots: list[Shot]) -> set[str]:
    roles: set[str] = set()
    for s in shots:
        roles.update(s.story_roles)
        roles.add(s.shot_type)
    return roles
