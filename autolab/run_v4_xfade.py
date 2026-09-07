"""One-shot runner for V4_xfade_soft experiment."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V4_DIR = ROOT / "Output" / "autolab" / "V4"
V3_BEST_SCORE = 8.15
TAG = "autolab_xfade"


def main() -> int:
    V4_DIR.mkdir(parents=True, exist_ok=True)

    print("=== V4_xfade_soft render ===", flush=True)
    # Isolate from V5 pacing gate.
    import os

    os.environ["WEDDING_V3_PACE_HOLD"] = "0"
    try:
        import wedding_v3.story as story_mod

        story_mod.PACE_HOLD_FLOOR = False
    except Exception:
        pass

    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V4",
        }
    )

    if not run_result.get("ok"):
        err = run_result.get("error", "unknown error")
        print(f"PIPELINE FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V4_xfade_soft",
            "status": "failed",
            "error": err,
            "v3_baseline": V3_BEST_SCORE,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V4_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V4_xfade_soft FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    # Ensure mp4s live under V4_DIR (run_dir should already be V4_DIR/autolab_xfade)
    for mp4 in run_dir.glob("*.mp4"):
        dest = V4_DIR / mp4.name
        if mp4.resolve() != dest.resolve() and not dest.exists():
            shutil.copy2(mp4, dest)

    eval_result = evaluate_run(run_dir, V3_BEST_SCORE)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = json.loads(leaderboard_path.read_text(encoding="utf-8")) if leaderboard_path.exists() else {}

    verdict = "KEEP" if eval_result.get("better_than_best") else "REJECT"
    eval_data = {
        "experiment": "V4_xfade_soft",
        "status": "completed",
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
    (V4_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    log_lines = [
        "V4_xfade_soft completed.",
        f"run_dir={run_dir}",
        f"best_score={eval_result.get('score')} (V3 baseline {V3_BEST_SCORE})",
        f"verdict={verdict}",
        f"rendered={[r.get('path') for r in leaderboard.get('rendered', [])]}",
    ]
    append_experiment_log("\n".join(log_lines))

    state = load_state()
    state.current_experiment = "V4_xfade_soft"
    state.current_version = "V4_xfade_soft"
    state.experiments_run += 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if eval_result.get("better_than_best"):
        state.best_version = "V4_xfade_soft"
        state.best_score = float(eval_result["score"])
    else:
        state.best_version = "V3"
        state.best_score = V3_BEST_SCORE
    save_state(state)

    print(json.dumps(eval_data, indent=2), flush=True)
    return 0 if run_result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
