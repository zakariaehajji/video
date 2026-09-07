"""One-shot runner for V5_pace_hold_floor experiment.

Hypothesis: Enforce minimum shot holds (especially emotional intro/outro) so
beat-snapping cannot create sub-1s cut sprays. Expect higher pacing score and
less stock-footage busyness vs V3 8.15.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V5_DIR = ROOT / "Output" / "autolab" / "V5"
V3_BEST_SCORE = 8.15
TAG = "autolab_pace_hold"


def main() -> int:
    V5_DIR.mkdir(parents=True, exist_ok=True)

    print("=== V5_pace_hold_floor render ===", flush=True)
    # Enable gated floor in wedding_v3.story for this process only.
    import os

    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    # Re-import / refresh flag if story already imported in-process.
    import wedding_v3.story as story_mod

    story_mod.PACE_HOLD_FLOOR = True

    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V5",
        }
    )

    if not run_result.get("ok"):
        err = run_result.get("error", "unknown error")
        print(f"PIPELINE FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V5_pace_hold_floor",
            "status": "failed",
            "error": err,
            "v3_baseline": V3_BEST_SCORE,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V5_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V5_pace_hold_floor FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V5_DIR / mp4.name
        if mp4.resolve() != dest.resolve() and not dest.exists():
            shutil.copy2(mp4, dest)

    eval_result = evaluate_run(run_dir, V3_BEST_SCORE)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = (
        json.loads(leaderboard_path.read_text(encoding="utf-8"))
        if leaderboard_path.exists()
        else {}
    )

    verdict = "KEEP" if eval_result.get("better_than_best") else "REJECT"
    eval_data = {
        "experiment": "V5_pace_hold_floor",
        "status": "completed",
        "hypothesis": "Min shot duration floor stops beat-snap micro-cuts; raises pacing",
        "v3_baseline": V3_BEST_SCORE,
        "best_score": eval_result.get("score"),
        "delta_vs_v3": eval_result.get("delta"),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": leaderboard.get("best"),
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V5_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V5_pace_hold_floor completed.",
                f"run_dir={run_dir}",
                f"best_score={eval_result.get('score')} (V3 baseline {V3_BEST_SCORE})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V5_pace_hold_floor"
    state.current_version = "V5_pace_hold_floor"
    state.experiments_run += 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if eval_result.get("better_than_best"):
        state.best_version = "V5_pace_hold_floor"
        state.best_score = float(eval_result["score"])
    save_state(state)

    print(json.dumps(eval_data, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
