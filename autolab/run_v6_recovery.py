"""V6 recovery: peak emotion floor after kiss/hug pool rebuild.

Prior V6 render scored 8.14 (REJECT): wedding_feeling=10 but music_sync
collapsed because any peak with emotion_score < 0.35 triggers critic penalty.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V6_DIR = ROOT / "Output" / "autolab" / "V6"
V5_BEST = 8.22
V3 = 8.15
TAG = "autolab_kiss_hug_v2"
PRIOR_V6 = 8.14


def main() -> int:
    V6_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    import wedding_v3.story as story_mod

    story_mod.PACE_HOLD_FLOOR = True

    print("=== V6 recovery render (peak emotion floor) ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V6",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V6_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    eval_result = evaluate_run(run_dir, V5_BEST)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = (
        json.loads(leaderboard_path.read_text(encoding="utf-8"))
        if leaderboard_path.exists()
        else {}
    )
    score = float(eval_result.get("score") or 0.0)
    verdict = "KEEP" if eval_result.get("better_than_best") else "REJECT"
    best = leaderboard.get("best") or {}
    best_src = best.get("path")
    promoted = None
    if verdict == "KEEP" and best_src and Path(best_src).exists():
        dest = ROOT / "Output" / "autolab" / "BEST_v6.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)

    eval_data = {
        "experiment": "V6_emotion_kiss_hug",
        "variant": "peak_emotion_floor_recovery",
        "status": "completed",
        "hypothesis": (
            "Kiss/hug pool + peak intimacy reserve + peak emotion floor "
            "restores music_sync while keeping wedding_feeling"
        ),
        "v5_baseline": V5_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v5": eval_result.get("delta"),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "prior_reject_score": PRIOR_V6,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V6_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V6_emotion_kiss_hug recovery (peak emotion floor).",
                f"run_dir={run_dir}",
                f"best_score={score} (V5 {V5_BEST}; prior V6 {PRIOR_V6})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V6_emotion_kiss_hug"
    state.current_version = "V6_emotion_kiss_hug"
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V6_emotion_kiss_hug"
        state.best_score = score
        state.failed_experiments = [
            x for x in (state.failed_experiments or []) if x != "V6_emotion_kiss_hug"
        ]
        state.last_strategy = "KEEP V6 recovery; next: title cards"
        state.next_tasks = [
            {
                "title": "V7_title_cards",
                "hypothesis": "Soft title/outro cards raise polish and wedding feeling",
                "priority": 1.0,
            },
            {
                "title": "V7_tears_reaction",
                "hypothesis": "Stronger tear/reaction cues lift emotion beyond proximity kiss/hug",
                "priority": 0.8,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V6_emotion_kiss_hug" not in fails:
            fails.append("V6_emotion_kiss_hug")
        state.failed_experiments = fails
        state.last_strategy = "REJECT V6 recovery; keep V5; next: title cards / peak payoff"
        state.next_tasks = [
            {
                "title": "V7_title_cards",
                "hypothesis": "Soft title/outro cards raise polish and wedding feeling",
                "priority": 1.0,
            },
            {
                "title": "V7_peak_payoff",
                "hypothesis": "Stronger peak shot selection to protect music_sync with intimacy cues",
                "priority": 0.85,
            },
        ]
    save_state(state)
    (ROOT / "autolab" / "state" / "task_queue.json").write_text(
        json.dumps(state.next_tasks, indent=2), encoding="utf-8"
    )
    print(json.dumps(eval_data, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
