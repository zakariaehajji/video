# Montage Craft Curriculum (machine + human)

This document encodes professional wedding-montage craft for the AutoLab editor.
It is **original pedagogy summary**, not a copy of any paid course.

## Goal

Make shot selection and pacing feel like a luxury wedding film, not a stock-clip slideshow.

## Story spine

Default emotional arc (map to music sections):

1. **Prep / detail** — rings, flowers, shoes, hands (invite the world in quietly)
2. **Portrait** — bride/groom identity, eyes, breath
3. **Ceremony tension** — aisle energy, vows-adjacent stillness
4. **Emotional peak** — kiss / hug / tears / reaction (protect duration)
5. **Couple** — togetherness, walk, embrace
6. **Celebration** — dance, guests, motion
7. **Resolution** — wide, quiet, leave on feeling not on busyness

Never open on peak. Never end on chaotic dance unless music demands it.

## Best-shot selection (what “good” looks like)

Prefer shots that score high on:

| Signal | Why |
|--------|-----|
| Face present + sharp | Identity and emotion |
| Smile / tears / reaction | Emotional truth |
| Kiss / hug intimacy | Wedding payoff |
| Stable framing | Cinematic confidence |
| Clean exposure | Professional polish |
| Mid-shot or close on peak | Emotional connection |

Reject / down-rank:

- Heavy blur or shake on emotional beats
- Back-of-head only on peaks
- Sub-1s spray cuts (stock-footage feeling)
- Same clip repeated back-to-back without motive
- Peak moments shorter than musical phrase

## Pacing grammar

- Cut on **musical phrases / section changes**, not every beat.
- Emotional intro/outro: hold **2.5–4.5s**.
- Peaks: hold **at least 2.0–3.5s** (linger).
- Motion/chorus: can be shorter, still avoid &lt;1.0s.
- Soft sections: prefer dissolve/xfade; peaks: hard cut.

## Continuity

- Prefer similar color/temperature across adjacent clips.
- Avoid jarring day/night or indoor/outdoor jumps without a bridge detail.
- Alternate scale: wide → medium → close, not close → close → close.

## Template recipes

JSON templates in `autolab/craft/templates/` (~24 recipes) and CapCut-style presets in
`autolab/craft/presets/` define role sequences, min/max durations, and xfade policy.
Pipeline: `run_candidates(..., craft_templates=...)`. Competitive notes:
`docs/COMPETITIVE_STRATEGY.md`.

## Critic checklist (human-like)

After auto scores, ask:

1. Would a filmmaker keep this cut?
2. Does emotion land, or only “pretty faces”?
3. Does music feel accompanied or ignored?
4. Is there dead air or choppy spray?
5. Does the ending feel resolved?

Honest scores beat inflated ones.
