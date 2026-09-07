"""One-shot runner for V8_tears_reaction experiment.

Hypothesis: Stronger tear/reaction cues (under-eye sheen + solemn face +
improved guest reaction) lift emotion beyond proximity kiss/hug while
keeping V5 pace-hold + V7 title cards.

Compares against V7 best (8.47). Never overwrites BEST_v7 / BEST_v3.
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

V8_DIR = ROOT / "Output" / "autolab" / "V8"
V7_BEST = 8.47
V6_BEST = 8.42
V5_BEST = 8.22
V3 = 8.15
TAG = "autolab_tears_reaction"


def _rebuild_shot_pool() -> dict:
    from wedding_v3.shots import CACHE_SCHEMA, build_pool

    vid_dir = ROOT / "resource" / "video" / "wedding_web"
    print(f"=== Force rebuild shot pool ({CACHE_SCHEMA}) ===", flush=True)
    shots = build_pool(vid_dir, force=True)
    kisses = [float(getattr(s, "kiss", 0.0) or 0.0) for s in shots]
    hugs = [float(getattr(s, "hug", 0.0) or 0.0) for s in shots]
    reactions = [float(getattr(s, "reaction", 0.0) or 0.0) for s in shots]
    tears = [float(getattr(s, "tears", 0.0) or 0.0) for s in shots]
    stats = {
        "n_shots": len(shots),
        "kiss_ge_040": sum(1 for k in kisses if k >= 0.40),
        "hug_ge_050": sum(1 for h in hugs if h >= 0.50),
        "reaction_ge_050": sum(1 for r in reactions if r >= 0.50),
        "tears_ge_042": sum(1 for t in tears if t >= 0.42),
        "kiss_max": round(max(kisses) if kisses else 0.0, 4),
        "hug_max": round(max(hugs) if hugs else 0.0, 4),
        "reaction_max": round(max(reactions) if reactions else 0.0, 4),
        "tears_max": round(max(tears) if tears else 0.0, 4),
        "cache_schema": CACHE_SCHEMA,
    }
    print(json.dumps(stats, indent=2), flush=True)
    return stats


def main() -> int:
    V8_DIR.mkdir(parents=True, exist_ok=True)

    # Keep V5/V6/V7 gates; tears/reaction live in emotion + ranking + critic.
    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
    import wedding_v3.story as story_mod
    import wedding_v3.titles as titles_mod
    import wedding_v3.critic as critic_mod
    import wedding_v3.cinematic as cine_mod

    story_mod.PACE_HOLD_FLOOR = True
    titles_mod.TITLE_CARDS = True
    critic_mod.TITLE_CARDS = True
    cine_mod.TITLE_CARDS = True

    pool_stats = _rebuild_shot_pool()

    print("=== V8_tears_reaction render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V8",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V8_tears_reaction",
            "status": "failed",
            "error": err,
            "v7_baseline": V7_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V8_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V8_tears_reaction FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V8_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    eval_result = evaluate_run(run_dir, V7_BEST)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v8.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V8_tears_reaction",
                hypothesis=(
                    "Stronger tear/reaction cues lift emotion beyond proximity kiss/hug"
                ),
                configuration={"tag": TAG, "cache_schema": pool_stats.get("cache_schema")},
                status="running",
            )
            lab_db.finish_experiment(
                eid,
                score=score,
                runtime=float(run_result.get("runtime") or 0.0),
                result=f"KEEP vs V7 {V7_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V8_tears_reaction",
                score,
                promoted,
                notes=f"tears/reaction KEEP delta={eval_result.get('delta')}",
                parent="V7_title_cards",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V8_tears_reaction",
        "status": "completed",
        "hypothesis": (
            "Stronger tear/reaction cues lift emotion beyond proximity kiss/hug "
            "while keeping pace-hold + title cards"
        ),
        "v7_baseline": V7_BEST,
        "v6_baseline": V6_BEST,
        "v5_baseline": V5_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v7": eval_result.get("delta"),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "pool_stats": pool_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V8_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V8_tears_reaction completed.",
                f"run_dir={run_dir}",
                f"pool={pool_stats}",
                f"best_score={score} (V7 baseline {V7_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V8_tears_reaction"
    state.current_version = "V8_tears_reaction"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V8_tears_reaction"
        state.best_score = score
        state.last_strategy = "KEEP V8 tears; next: visual_quality"
        state.next_tasks = [
            {
                "title": "V9_visual_quality",
                "hypothesis": "Prefer higher cinematic_quality shots to lift visual_quality ~6.2",
                "priority": 1.0,
            },
            {
                "title": "V9_continuity_color",
                "hypothesis": "Color/continuity matching reduces stock-footage feeling",
                "priority": 0.8,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V8_tears_reaction" not in fails:
            fails.append("V8_tears_reaction")
        state.failed_experiments = fails
        state.last_strategy = "REJECT V8 tears; keep V7; next: visual_quality"
        state.next_tasks = [
            {
                "title": "V8_visual_quality",
                "hypothesis": "Prefer higher cinematic_quality shots to lift visual_quality ~6.2",
                "priority": 1.0,
            },
            {
                "title": "V8_reaction_thresholds",
                "hypothesis": "Tune tear/reaction thresholds if pool positives are noisy",
                "priority": 0.7,
            },
        ]
    save_state(state)
    (ROOT / "autolab" / "state" / "task_queue.json").write_text(
        json.dumps(state.next_tasks, indent=2), encoding="utf-8"
    )

    pending_path = ROOT / "autolab" / "pending_jobs.json"
    try:
        jobs = json.loads(pending_path.read_text(encoding="utf-8"))
    except Exception:
        jobs = []
    jobs = [j for j in jobs if j.get("id") != "V8_tears_reaction"]
    jobs.append(
        {
            "id": "V8_tears_reaction",
            "script": "autolab/run_v8_tears.py",
            "status": "done",
            "priority": 5,
            "hypothesis": "Stronger tear/reaction cues lift emotion beyond proximity kiss/hug",
            "depends_on": "V7_title_cards",
            "returncode": 0 if verdict == "KEEP" else 1,
            "score": score,
            "verdict": verdict,
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": f"V8_tears_reaction {verdict} {score:.2f} vs V7 {V7_BEST}",
        "best_version": state.best_version if verdict == "KEEP" else "V7_title_cards",
        "best_score": state.best_score if verdict == "KEEP" else V7_BEST,
        "renders_executed": True,
    }
    (ROOT / "autolab" / "results" / "BLOCKER.json").write_text(
        json.dumps(blocker, indent=2), encoding="utf-8"
    )

    print(json.dumps(eval_data, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
