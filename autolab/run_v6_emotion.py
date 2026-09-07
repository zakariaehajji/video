"""One-shot runner for V6_emotion_kiss_hug experiment.

Hypothesis: Force-rebuild shot pool with kiss/hug/reaction geometry, then
prefer intimacy on peaks (reserve early). Raises emotion + wedding_feeling
vs smile-only V5 while keeping pace-hold floor.

Compares against V5 best (8.22), not only V3 (8.15).
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
V5_BEST_SCORE = 8.22
V3_BASELINE = 8.15
TAG = "autolab_kiss_hug"


def _rebuild_shot_pool() -> dict:
    from wedding_v3.shots import CACHE_SCHEMA, build_pool

    vid_dir = ROOT / "resource" / "video" / "wedding_web"
    print(f"=== Force rebuild shot pool ({CACHE_SCHEMA}) ===", flush=True)
    shots = build_pool(vid_dir, force=True)
    kisses = [float(getattr(s, "kiss", 0.0) or 0.0) for s in shots]
    hugs = [float(getattr(s, "hug", 0.0) or 0.0) for s in shots]
    reactions = [float(getattr(s, "reaction", 0.0) or 0.0) for s in shots]
    stats = {
        "n_shots": len(shots),
        "kiss_ge_040": sum(1 for k in kisses if k >= 0.40),
        "hug_ge_050": sum(1 for h in hugs if h >= 0.50),
        "reaction_ge_055": sum(1 for r in reactions if r >= 0.55),
        "kiss_max": round(max(kisses) if kisses else 0.0, 4),
        "hug_max": round(max(hugs) if hugs else 0.0, 4),
        "reaction_max": round(max(reactions) if reactions else 0.0, 4),
        "cache_schema": CACHE_SCHEMA,
    }
    print(json.dumps(stats, indent=2), flush=True)
    return stats


def main() -> int:
    V6_DIR.mkdir(parents=True, exist_ok=True)
    pool_stats = _rebuild_shot_pool()

    print("=== V6_emotion_kiss_hug render ===", flush=True)
    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    import wedding_v3.story as story_mod

    story_mod.PACE_HOLD_FLOOR = True

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
        err = run_result.get("error", "unknown error")
        print(f"PIPELINE FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V6_emotion_kiss_hug",
            "status": "failed",
            "error": err,
            "v5_baseline": V5_BEST_SCORE,
            "v3_baseline": V3_BASELINE,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V6_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V6_emotion_kiss_hug FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V6_DIR / mp4.name
        if mp4.resolve() != dest.resolve() and not dest.exists():
            shutil.copy2(mp4, dest)

    # Compare against current best (V5), not only V3.
    eval_result = evaluate_run(run_dir, V5_BEST_SCORE)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = (
        json.loads(leaderboard_path.read_text(encoding="utf-8"))
        if leaderboard_path.exists()
        else {}
    )

    score = float(eval_result.get("score") or 0.0)
    verdict = "KEEP" if eval_result.get("better_than_best") else "REJECT"
    best_src = None
    if isinstance(leaderboard.get("best"), dict):
        best_src = leaderboard["best"].get("path")

    promoted = None
    if verdict == "KEEP" and best_src and Path(best_src).exists():
        dest = ROOT / "Output" / "autolab" / "BEST_v6.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        # Do not touch Output/wedding_v3/BEST_v3.mp4 or BEST_v5.mp4

    critique = eval_result.get("critique") or {}
    eval_data = {
        "experiment": "V6_emotion_kiss_hug",
        "status": "completed",
        "hypothesis": (
            "Rebuild shot pool with kiss/hug/reaction cues + peak intimacy reserve "
            "raises emotion and wedding_feeling vs smile-only V5"
        ),
        "v5_baseline": V5_BEST_SCORE,
        "v3_baseline": V3_BASELINE,
        "best_score": score,
        "delta_vs_v5": eval_result.get("delta"),
        "delta_vs_v3": round(score - V3_BASELINE, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "pool_stats": pool_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": leaderboard.get("best"),
        "promoted": promoted,
        "critique": critique,
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V6_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V6_emotion_kiss_hug completed.",
                f"run_dir={run_dir}",
                f"pool={pool_stats}",
                f"best_score={score} (V5 baseline {V5_BEST_SCORE})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V6_emotion_kiss_hug"
    state.current_version = "V6_emotion_kiss_hug"
    state.experiments_run += 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V6_emotion_kiss_hug"
        state.best_score = score
        state.last_strategy = "KEEP V6; next: title cards / continuity / tears"
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
        state.failed_experiments = list(state.failed_experiments or []) + [
            "V6_emotion_kiss_hug"
        ]
        state.last_strategy = "REJECT V6; keep V5; next: title cards or tear/reaction"
        state.next_tasks = [
            {
                "title": "V7_title_cards",
                "hypothesis": "Soft title/outro cards raise polish and wedding feeling",
                "priority": 1.0,
            },
            {
                "title": "V7_intimacy_thresholds",
                "hypothesis": "Tune kiss/hug thresholds if pool has weak positives",
                "priority": 0.7,
            },
        ]
    save_state(state)

    # Sync task queue from state next_tasks
    queue_path = ROOT / "autolab" / "state" / "task_queue.json"
    queue_path.write_text(json.dumps(state.next_tasks, indent=2), encoding="utf-8")

    print(json.dumps(eval_data, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
