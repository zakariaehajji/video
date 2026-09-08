"""Generate additional montage craft JSON templates (legal pedagogy recipes)."""
from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).resolve().parent / "templates"

BASE_ARCS = {
    "emotion_first": {
        "intro": ["detail", "portrait", "wide"],
        "build": ["portrait", "detail", "couple"],
        "verse": ["couple", "portrait", "detail"],
        "chorus": ["couple", "portrait", "motion"],
        "peak": ["couple", "portrait", "motion"],
        "outro": ["wide", "couple", "detail"],
    },
    "detail_open": {
        "intro": ["detail", "detail", "wide"],
        "build": ["detail", "portrait", "wide"],
        "verse": ["portrait", "couple", "detail"],
        "chorus": ["couple", "motion", "portrait"],
        "peak": ["couple", "portrait", "motion"],
        "outro": ["wide", "detail", "couple"],
    },
    "portrait_led": {
        "intro": ["portrait", "detail", "wide"],
        "build": ["portrait", "portrait", "detail"],
        "verse": ["portrait", "couple", "detail"],
        "chorus": ["couple", "portrait", "motion"],
        "peak": ["portrait", "couple", "motion"],
        "outro": ["couple", "wide", "portrait"],
    },
    "energy_led": {
        "intro": ["wide", "motion", "detail"],
        "build": ["motion", "wide", "portrait"],
        "verse": ["motion", "couple", "portrait"],
        "chorus": ["motion", "couple", "wide"],
        "peak": ["couple", "motion", "portrait"],
        "outro": ["wide", "motion", "couple"],
    },
    "quiet_luxury": {
        "intro": ["detail", "wide", "detail"],
        "build": ["wide", "portrait", "detail"],
        "verse": ["couple", "detail", "portrait"],
        "chorus": ["couple", "portrait", "wide"],
        "peak": ["couple", "portrait", "detail"],
        "outro": ["wide", "detail", "couple"],
    },
}

SPECS = [
    ("prep_to_peak", "Prep detail into emotional peak", "emotional", "A_emotion", 38, 1.9, 4.2, 2.8, "detail_open", True, True),
    ("wide_bookends", "Wide establish and resolve", "classic", "B_story_music", 40, 2.0, 4.5, 2.6, "quiet_luxury", True, True),
    ("intimate_close", "Close faces and intimacy", "emotional", "C_peak_payoff", 36, 2.0, 4.0, 3.0, "portrait_led", True, True),
    ("dance_floor", "Reception energy cuts", "energetic", "D_balanced", 42, 1.2, 3.2, 2.0, "energy_led", False, False),
    ("slow_burn", "Long holds, soft dissolves", "emotional", "A_emotion", 45, 2.4, 5.0, 3.2, "quiet_luxury", True, True),
    ("highlight_90s", "90s highlight reel pacing", "classic", "D_balanced", 90, 1.6, 4.0, 2.5, "emotion_first", True, True),
    ("vow_focus", "Vow / reaction protection", "emotional", "C_peak_payoff", 38, 2.2, 4.8, 3.4, "portrait_led", True, True),
    ("family_warmth", "Guests and family warmth", "classic", "B_story_music", 40, 1.8, 4.0, 2.5, "detail_open", True, True),
    ("golden_hour", "Warm couple walk energy", "emotional", "A_emotion", 38, 2.0, 4.5, 2.8, "emotion_first", True, True),
    ("ring_to_kiss", "Detail ring into kiss peak", "emotional", "C_peak_payoff", 36, 1.9, 4.2, 3.0, "detail_open", True, True),
    ("first_look", "First-look intimacy arc", "emotional", "A_emotion", 34, 2.1, 4.5, 3.0, "portrait_led", True, True),
    ("guest_reactions", "Reaction cutaways around peak", "classic", "B_story_music", 38, 1.7, 3.8, 2.4, "emotion_first", True, True),
    ("cinematic_walk", "Couple walk cinematic holds", "emotional", "D_balanced", 42, 2.2, 5.0, 2.8, "quiet_luxury", True, True),
    ("party_montage", "Short party montage", "energetic", "D_balanced", 30, 1.0, 2.8, 1.8, "energy_led", False, False),
    ("tear_peak", "Tears / solemn peak linger", "emotional", "C_peak_payoff", 40, 2.3, 4.8, 3.5, "portrait_led", True, True),
    ("balanced_classic", "Classic agency delivery", "classic", "D_balanced", 38, 1.8, 4.0, 2.5, "emotion_first", True, True),
    ("soft_open_hard_peak", "Soft open, hard climax", "emotional", "C_peak_payoff", 38, 2.0, 4.2, 2.9, "quiet_luxury", True, True),
    ("story_spine", "Strict story spine roles", "classic", "B_story_music", 40, 2.0, 4.5, 2.7, "detail_open", True, True),
]


def main() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    for (
        tid,
        title,
        style,
        profile,
        dur,
        mn,
        mx,
        pmin,
        arc_key,
        pace,
        peak,
    ) in SPECS:
        path = DIR / f"{tid}.json"
        if path.exists():
            continue
        data = {
            "id": tid,
            "title": title,
            "style": style,
            "target_duration": dur,
            "description": title,
            "min_shot_dur": mn,
            "max_shot_dur": mx,
            "peak_min_dur": pmin,
            "prefer_xfade_sections": ["intro", "outro", "build"] if pace else ["outro"],
            "hard_cut_on_peak": True,
            "role_arc": BASE_ARCS[arc_key],
            "ranking_profile": profile,
            "pace_hold": pace,
            "peak_hold": peak,
        }
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("wrote", path.name)


if __name__ == "__main__":
    main()
