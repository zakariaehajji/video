"""Automatic montage critic with measurable 0-10 scores."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from wedding_v3.ranking import RankedPick
from wedding_v3.shots import color_distance
from wedding_v3.titles import TITLE_CARDS

COLOR_CONTINUITY = os.environ.get("WEDDING_V3_COLOR_CONTINUITY", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# V11: duration-weight emotion so lingering on climaxes is reflected in score.
PEAK_HOLD = os.environ.get("WEDDING_V3_PEAK_HOLD", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)


@dataclass
class Critique:
    visual_quality: float
    story_coherence: float
    emotion: float
    music_sync: float
    wedding_feeling: float
    variety: float
    continuity: float
    pacing: float
    technical_quality: float
    polish: float
    overall: float
    problems: list[str]
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp10(x: float) -> float:
    return round(max(0.0, min(10.0, x)), 2)


def critique_plan(picks: list[RankedPick], profile: str = "") -> Critique:
    if not picks:
        return Critique(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ["empty plan"], ["generate shots"])

    n = len(picks)
    problems: list[str] = []
    recs: list[str] = []

    tech = sum(p.shot.technical_quality for p in picks) / n
    visual = sum(p.shot.cinematic_quality for p in picks) / n
    if PEAK_HOLD:
        # Linger on emotional climaxes should raise perceived emotion (duration-weighted).
        tw = sum(max(0.35, float(p.beat.dur)) for p in picks) or float(n)
        emo = sum(p.shot.emotion_score * max(0.35, float(p.beat.dur)) for p in picks) / tw
    else:
        emo = sum(p.shot.emotion_score for p in picks) / n
    peak_slots = [p for p in picks if p.beat.is_peak]
    if peak_slots and PEAK_HOLD:
        pw = sum(max(0.35, float(p.beat.dur)) for p in peak_slots) or float(len(peak_slots))
        peak_emo = (
            sum(p.shot.emotional_peak_score * max(0.35, float(p.beat.dur)) for p in peak_slots)
            / pw
        )
    else:
        peak_emo = (
            sum(p.shot.emotional_peak_score for p in peak_slots) / len(peak_slots)
            if peak_slots else emo
        )

    videos = [p.shot.video for p in picks]
    uniq = len(set(videos))
    variety = uniq / max(1, min(11, n))
    # consecutive same video
    consec = sum(1 for a, b in zip(videos, videos[1:]) if a == b)
    continuity = 1.0 - min(1.0, consec / max(1, n - 1))

    # Color-jump continuity: large LAB jumps feel like stock-footage collage.
    harsh_color = 0
    if COLOR_CONTINUITY and n >= 2:
        dists = [color_distance(a.shot, b.shot) for a, b in zip(picks, picks[1:])]
        mean_jump = sum(dists) / len(dists)
        # mean_jump ~0.2 good, ~0.6 harsh
        color_cont = max(0.0, 1.0 - min(1.0, (mean_jump - 0.12) / 0.55))
        continuity = 0.55 * continuity + 0.45 * color_cont
        harsh_color = sum(1 for d in dists if d >= 0.55)
        if harsh_color >= max(2, n // 5):
            problems.append("harsh color jumps between cuts")
            recs.append("prefer palette-similar adjacent shots or grade toward film look")

    roles = [p.beat.role for p in picks]
    role_counts = Counter(roles)
    # story: prefer presence of detail early and couple/wide late
    story = 0.55
    early = roles[: max(1, n // 4)]
    late = roles[-max(1, n // 4) :]
    if any(r == "detail" for r in early):
        story += 0.15
    if any(r in ("couple", "portrait") for r in roles[n // 3 : 2 * n // 3]):
        story += 0.15
    if any(r in ("wide", "couple") for r in late):
        story += 0.15
    if role_counts.get("portrait", 0) > n * 0.55:
        story -= 0.2
        problems.append("bride/portrait appears too many times")
        recs.append("replace mid-film portraits with couple/motion/detail")

    # music sync proxy: average rank score + peak alignment
    music = sum(p.score for p in picks) / n
    if peak_slots:
        weak_peak = sum(1 for p in peak_slots if p.shot.emotion_score < 0.35)
        if weak_peak:
            problems.append("music peak has weak visual payoff")
            recs.append("move highest-smile shot to peak section")
            music *= 0.85
        else:
            music = min(1.0, music + 0.08)

    # pacing: duration variance
    durs = [p.beat.dur for p in picks]
    mean_d = sum(durs) / n
    var = sum((d - mean_d) ** 2 for d in durs) / n
    pacing = 0.75 if 0.05 < var < 0.6 else 0.55
    if mean_d < 0.85:
        pacing -= 0.1
        problems.append("pacing too choppy")
    if mean_d > 2.2:
        pacing -= 0.1
        problems.append("pacing too slow")

    # wedding feeling
    tags = set()
    for p in picks:
        tags.update(p.shot.semantic_tags)
    wedding = 0.4
    for t in ("detail", "portrait", "couple", "smile", "emotional_peak", "kiss", "hug", "reaction", "tears"):
        if t in tags or any(t in p.shot.story_roles for p in picks):
            wedding += 0.08
    wedding = min(1.0, wedding)
    if "kiss" in tags:
        wedding = min(1.0, wedding + 0.08)
        # Strong intimacy improves emotion dimension perception
        emo = min(1.0, emo + 0.05)
    if "hug" in tags:
        wedding = min(1.0, wedding + 0.04)
    if "tears" in tags:
        wedding = min(1.0, wedding + 0.07)
        emo = min(1.0, emo + 0.06)
        peak_emo = min(1.0, peak_emo + 0.04)
    if "reaction" in tags:
        wedding = min(1.0, wedding + 0.04)
        emo = min(1.0, emo + 0.03)

    polish = 0.55
    slow = sum(1 for p in picks if p.beat.want_slowmo)
    xfade = sum(1 for p in picks if p.beat.want_xfade)
    if 1 <= slow <= max(2, n // 5):
        polish += 0.15
    elif slow > n // 3:
        polish -= 0.1
        problems.append("too much slow motion")
    if xfade:
        polish += 0.1
    # V7 soft title/outro cards: professional wedding-film bookends.
    if TITLE_CARDS:
        polish = min(1.0, polish + 0.18)
        wedding = min(1.0, wedding + 0.06)
    if harsh_color >= max(2, n // 5):
        polish = max(0.35, polish - 0.08)

    if consec >= 3:
        problems.append("same source repeated consecutively")
        recs.append("enforce stronger variety penalty")
    if picks and picks[-1].shot.emotion_score < 0.3 and picks[-1].beat.role != "wide":
        problems.append("final shot is not strong enough")
        recs.append("use wider/couple ending with higher quality")

    # peak too early
    if peak_slots:
        first_peak_i = next(i for i, p in enumerate(picks) if p.beat.is_peak)
        if first_peak_i < n * 0.25 and peak_emo > 0.6:
            problems.append("emotional peak occurs too early")
            recs.append("reserve strongest smile/kiss for later chorus/peak")

    overall_01 = (
        0.12 * visual
        + 0.14 * story
        + 0.16 * ((emo + peak_emo) / 2)
        + 0.14 * music
        + 0.12 * wedding
        + 0.10 * variety
        + 0.08 * continuity
        + 0.07 * pacing
        + 0.04 * tech
        + 0.03 * polish
    )

    return Critique(
        visual_quality=_clamp10(visual * 10),
        story_coherence=_clamp10(story * 10),
        emotion=_clamp10(((emo + peak_emo) / 2) * 10),
        music_sync=_clamp10(music * 10),
        wedding_feeling=_clamp10(wedding * 10),
        variety=_clamp10(variety * 10),
        continuity=_clamp10(continuity * 10),
        pacing=_clamp10(pacing * 10),
        technical_quality=_clamp10(tech * 10),
        polish=_clamp10(polish * 10),
        overall=_clamp10(overall_01 * 10),
        problems=problems or ["none critical"],
        recommendations=recs or ["maintain current structure"],
    )


def save_critique(c: Critique, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(c.to_dict(), indent=2), encoding="utf-8")
