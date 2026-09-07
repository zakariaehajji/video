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


ARC_BY_SECTION = {
    "intro": ["detail", "wide", "portrait"],
    "build": ["portrait", "detail", "couple"],
    "verse": ["couple", "portrait", "motion"],
    "chorus": ["couple", "motion", "portrait"],
    "peak": ["couple", "portrait", "motion"],
    "outro": ["wide", "couple", "detail"],
}


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
) -> list[PlannedBeat]:
    """Build adaptive beat list. Skips roles that have no footage."""
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

    for si, sec in enumerate(sections):
        s0, s1 = float(sec["start"]), float(min(sec["end"], duration))
        if s1 - s0 < 0.6:
            continue
        label = sec.get("label", "verse")
        prefs = [r for r in ARC_BY_SECTION.get(label, ["couple"]) if r in available_roles]
        if not prefs:
            prefs = list(available_roles) or ["couple"]

        energy = float(sec.get("mean_energy", _section_energy(analysis, s0, s1)))
        if style == "emotional":
            # Longer holds: V3 emotional pacing felt busy / stock-footage-like.
            if PACE_HOLD_FLOOR:
                # V5: raise bases so intro isn't a spray of ~0.7s cuts.
                # Target mean hold ~1.5–2.0s (avoid critic "too slow" >2.35).
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

        if energy > 0.7:
            base *= 0.9
        if label == "peak":
            if PACE_HOLD_FLOOR:
                base = min(base, 1.55 if style == "emotional" else 1.35)
                min_dur = min(min_dur, 1.0 if style == "emotional" else 0.85)
            else:
                base = min(base, 1.45 if style == "emotional" else 1.35)

        t = s0
        idx = 0
        while t < s1 - 0.45:
            role = prefs[idx % len(prefs)]
            dur = base
            if PACE_HOLD_FLOOR:
                # Snap only when gap is long enough to hold (no micro-cut sprays).
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
            end = min(s1, t + dur)
            if end - t < (min(0.55, min_dur * 0.55) if PACE_HOLD_FLOOR else 0.55):
                break
            if PACE_HOLD_FLOOR:
                rem = s1 - end
                if 0 < rem < min_dur * 0.75:
                    end = s1

            near_peak = any(abs((t + end) / 2 - p) < 1.2 for p in peaks) or label == "peak"
            # Intro/outro stay soft for dissolves; don't mark them peak from nearby music peaks.
            is_peak = label == "peak" or (
                near_peak and label in ("chorus", "verse", "build")
            )
            want_slow = is_peak and role in ("couple", "portrait") and energy > 0.45
            want_xfade = (
                label in ("intro", "outro", "build")
                and energy < 0.55
                and style != "energetic"
                and not is_peak
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

    # V5: fewer/longer beats make raw peak-slowmo density too high for the critic.
    # Cap to the polish sweet-spot (1..n//5), couple-only, preserving earliest peaks.
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
        role = "wide" if "wide" in available_roles else ("couple" if "couple" in available_roles else prefs[0])
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


def available_roles_from_shots(shots: list[Shot]) -> set[str]:
    roles: set[str] = set()
    for s in shots:
        roles.update(s.story_roles)
        roles.add(s.shot_type)
    return roles
