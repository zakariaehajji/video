"""Adaptive wedding story planning from music sections + available shot roles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wedding_v3.music import MusicAnalysis
from wedding_v3.shots import Shot


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
            base = 2.4 if label in ("intro", "outro") else 1.7
        elif style == "energetic":
            base = 1.9 if label in ("intro", "outro") else 1.25
        else:
            base = 2.6 if label in ("intro", "outro") else 1.9 if label == "build" else 1.55

        if energy > 0.7:
            base *= 0.9
        if label == "peak":
            base = min(base, 1.35)

        t = s0
        idx = 0
        while t < s1 - 0.45:
            role = prefs[idx % len(prefs)]
            dur = base
            future_beats = [b for b in beat_times if b > t + 0.5]
            if future_beats:
                gap = future_beats[0] - t
                if 0.7 <= gap <= 2.8:
                    dur = gap
            end = min(s1, t + dur)
            if end - t < 0.55:
                break

            near_peak = any(abs((t + end) / 2 - p) < 1.2 for p in peaks) or label == "peak"
            want_slow = near_peak and role in ("couple", "portrait") and energy > 0.45
            want_xfade = label in ("intro", "outro", "build") and energy < 0.55 and style != "energetic"

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
                    is_peak=near_peak or label == "peak",
                )
            )
            t = end
            idx += 1

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
