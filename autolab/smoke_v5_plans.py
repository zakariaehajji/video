"""Plan-only smoke test for V5 pacing (no ffmpeg render).

Compares critic scores with PACE_HOLD off vs on using the cached shot pool.
Writes Output/autolab/V5/PLAN_SMOKE.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from autolab.paths import ROOT

OUT = ROOT / "Output" / "autolab" / "V5"
CACHE = ROOT / "Output" / "v3_cache"
AUDIO = ROOT / "resource" / "audio" / "wedding_web" / "music_428.mp3"


def _run_once(pace_hold: bool) -> dict:
    os.environ["WEDDING_V3_PACE_HOLD"] = "1" if pace_hold else "0"
    import wedding_v3.story as story_mod
    from wedding_v3.critic import critique_plan
    from wedding_v3.music import MusicAnalysis
    from wedding_v3.ranking import allocate
    from wedding_v3.shots import load_pool
    from wedding_v3.story import available_roles_from_shots, plan_story

    story_mod.PACE_HOLD_FLOOR = pace_hold
    shots = load_pool(CACHE / "shots" / "pool.json")
    roles = available_roles_from_shots(shots)
    analysis = MusicAnalysis(AUDIO)
    analysis.analyze()

    results = {}
    for style in ("emotional", "classic"):
        beats = plan_story(analysis, roles, target_duration=38.0, style=style)
        picks = allocate(beats, shots, profile="A_emotion")
        crit = critique_plan(picks, profile="A_emotion")
        durs = [p.beat.dur for p in picks]
        results[style] = {
            "n_shots": len(picks),
            "mean_dur": round(sum(durs) / max(1, len(durs)), 3),
            "min_dur": round(min(durs), 3) if durs else 0,
            "short_frac_lt1s": round(sum(1 for d in durs if d < 1.0) / max(1, len(durs)), 3),
            "critique": crit.to_dict(),
        }
    return results


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = _run_once(False)
    paced = _run_once(True)
    payload = {
        "experiment": "V5_pace_hold_floor_plan_smoke",
        "status": "completed",
        "note": "Plan+critic only; no mp4 render",
        "baseline_pace_hold_off": baseline,
        "paced_hold_on": paced,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = OUT / "PLAN_SMOKE.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    print(f"Wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
