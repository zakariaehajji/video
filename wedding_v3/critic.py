"""Automatic montage critic with measurable 0-10 scores."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from wedding_v3 import titles as titles_mod
from wedding_v3.ranking import RankedPick
from wedding_v3.shots import color_distance

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
# V12: reward music-section ↔ story-role alignment in music_sync.
MUSIC_SECTION_ROLES = os.environ.get("WEDDING_V3_MUSIC_SECTION_ROLES", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)

_SECTION_ROLE_OK = {
    "intro": {"detail", "wide", "portrait"},
    "build": {"portrait", "detail", "couple"},
    "verse": {"couple", "portrait", "detail", "motion"},
    "chorus": {"couple", "motion", "portrait"},
    "peak": {"couple", "portrait", "motion"},
    "outro": {"wide", "couple", "detail"},
}


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


def critique_plan(
    picks: list[RankedPick],
    profile: str = "",
    craft: dict[str, Any] | None = None,
) -> Critique:
    if not picks:
        return Critique(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ["empty plan"], ["generate shots"])

    n = len(picks)
    problems: list[str] = []
    recs: list[str] = []
    craft = craft or {}

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

    # V12: diagnose section↔role grammar (no free score inflate — ranking must earn it).
    if MUSIC_SECTION_ROLES:
        hits = 0
        for p in picks:
            ok = _SECTION_ROLE_OK.get(p.beat.section) or {p.beat.role}
            if p.beat.role in ok:
                hits += 1
        align = hits / n
        peak_human = [
            p
            for p in peak_slots
            if p.shot.shot_type in ("couple", "portrait")
            or p.beat.role in ("couple", "portrait")
        ]
        peak_ratio = (len(peak_human) / len(peak_slots)) if peak_slots else 0.0
        if peak_slots and peak_ratio < 0.55:
            problems.append("peak section leans on non-intimate roles")
            recs.append("prefer couple/portrait on musical climax")
        if align < 0.60:
            problems.append("music sections poorly matched to story roles")
            recs.append("tighten section→role arc mapping")
        # Tiny earned bump only when climax is mostly intimate + grammar is solid.
        if align >= 0.85 and peak_ratio >= 0.70:
            music = min(1.0, music + 0.03)

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
    # CapCut gap: cut-every-beat spray (many sub-1.1s holds).
    spray = sum(1 for d in durs if d < 1.1)
    if spray >= max(4, n // 3):
        pacing = max(0.35, pacing - 0.12)
        problems.append("cut-every-beat spray (craft)")
        recs.append("prefer phrase/downbeat holds; denser cuts only on chorus/peak")
    # 20min course sprint: phrase-hold too weak when overall + peaks are both short.
    peak_durs = [p.beat.dur for p in peak_slots] if peak_slots else []
    mean_peak = (sum(peak_durs) / len(peak_durs)) if peak_durs else mean_d
    if mean_d < 1.3 and mean_peak < 2.0:
        pacing = max(0.35, pacing - 0.08)
        problems.append("phrase-hold too weak (course sprint)")
        recs.append("raise min/peak holds; cut on phrases not every beat")

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
    if titles_mod.TITLE_CARDS:
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

    # Craft checklist: eye contact proxy, dead air, jump cuts, music-phrase holds.
    craft_bonus = 0.0
    peak_no_face = sum(1 for p in peak_slots if p.shot.faces < 1)
    if peak_no_face:
        problems.append("peak lacks eye-contact / face (craft)")
        recs.append("place sharp face close-ups on emotional peaks")
        craft_bonus -= 0.03 * peak_no_face
    soft_peaks = sum(
        1
        for p in peak_slots
        if float(getattr(p.shot, "sharpness", 0.0) or 0.0) < 0.45
    )
    if soft_peaks:
        problems.append("soft / blurry peak frames (craft)")
        craft_bonus -= 0.02 * soft_peaks
    micro = sum(1 for p in picks if p.beat.dur < 1.0)
    if micro >= max(3, n // 4):
        problems.append("dead-air risk from micro-cuts (craft)")
        recs.append("hold emotional phrases; cut on section changes")
        pacing = max(0.35, pacing - 0.08)
        craft_bonus -= 0.04
    # Jump cuts: hard consecutive same-role + large color jump feels stocky.
    jumpish = 0
    for a, b in zip(picks, picks[1:]):
        if a.beat.want_xfade or b.beat.want_xfade:
            continue
        if a.beat.role == b.beat.role and a.shot.video != b.shot.video:
            if color_distance(a.shot, b.shot) >= 0.55:
                jumpish += 1
    if jumpish >= 2:
        problems.append("jump-cut collage feel (craft)")
        recs.append("bridge with detail or soften with xfade on soft sections")
        continuity = max(0.35, continuity - 0.06)
        craft_bonus -= 0.03
    # Music phrase alignment: mean hold should respect craft min when provided.
    craft_min = float(craft.get("min_shot_dur") or 0)
    if craft_min > 0 and mean_d + 0.05 < craft_min * 0.85:
        problems.append("holds shorter than craft template phrase floor")
        pacing = max(0.35, pacing - 0.06)
        craft_bonus -= 0.03
    elif craft_min > 0 and mean_d >= craft_min * 0.95:
        craft_bonus += 0.02
    # Prefer intimate climax when template asks for peak_hold.
    if craft.get("peak_hold") and peak_slots:
        intimate = sum(
            1
            for p in peak_slots
            if p.shot.shot_type in ("couple", "portrait") or p.shot.faces >= 1
        )
        if intimate / len(peak_slots) >= 0.7:
            craft_bonus += 0.025
            emo = min(1.0, emo + 0.02)
        else:
            problems.append("craft peak_hold not met with intimate shots")
            craft_bonus -= 0.02

    # Free-course Kuleshov: intimacy should often be followed by a readable face.
    for a, b in zip(picks, picks[1:]):
        a_int = max(
            float(getattr(a.shot, "kiss", 0.0) or 0.0),
            float(getattr(a.shot, "hug", 0.0) or 0.0),
            float(getattr(a.shot, "tears", 0.0) or 0.0),
        )
        if a_int >= 0.45 and a.beat.is_peak:
            if b.shot.faces < 1 and float(getattr(b.shot, "reaction", 0.0) or 0.0) < 0.4:
                problems.append("missing reaction after intimacy (Kuleshov)")
                recs.append("follow kiss/hug/tears with a portrait or guest reaction")
                craft_bonus -= 0.02
                break

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
        + craft_bonus
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
