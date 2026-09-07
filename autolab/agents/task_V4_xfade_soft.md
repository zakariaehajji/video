# Autolab task: V4_xfade_soft

**Hypothesis:** Soft xfades on intro/outro raise polish without hurting sync

**Category:** editing

**Expected gain:** 0.25

**Rationale:** Polish/continuity gap vs best score

## Cursor Agent instructions

Improve cinematic.py so soft sections use real xfade (not cut-only). Keep hard cuts on peaks. Re-render top emotional candidates.

## Pipeline config

```json
{
  "styles": [
    "emotional",
    "classic"
  ],
  "profiles": [
    "A_emotion"
  ],
  "render_top": 2,
  "tag": "autolab_xfade",
  "audio_stem": "music_428"
}
```

When done: update autolab state via MCP `update_lab_state` / `record_experiment_result`.
Never overwrite the previous BEST without archiving.
