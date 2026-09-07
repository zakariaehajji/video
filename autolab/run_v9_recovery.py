"""V9 recovery: variety-safe visual boost after V9v1 REJECT.

V9v1 lifted visual 6.37→6.56 but overall fell 8.60→8.44 because hard
top-CQ pool filtering caused consecutive same-source repeats (variety 6.36).

Recovery: keep soft CQ floors/boosts + sharper visual weights; remove hard
pool filter; strengthen same-video variety/continuity penalties.
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

V9_DIR = ROOT / "Output" / "autolab" / "V9"
V8_BEST = 8.60
V9_PRIOR = 8.44
V3 = 8.15
TAG = "autolab_visual_quality_v2"


def _plan_visual_stats(run_dir: Path) -> dict:
    from wedding_v3.shots import load_pool

    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    by_id = {}
    if pool_path.exists():
        try:
            shots = load_pool(pool_path)
            by_id = {s.id: s for s in shots}
        except Exception:
            by_id = {}
    lb = run_dir / "leaderboard.json"
    if not lb.exists():
        return {}
    data = json.loads(lb.read_text(encoding="utf-8"))
    best = data.get("best") or {}
    name = best.get("name")
    if not name:
        return {}
    plan_path = run_dir / "plans" / f"{name}.json"
    if not plan_path.exists():
        return {}
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    picks = plan.get("picks") or []
    cqs, tqs, sharps = [], [], []
    for p in picks:
        s = by_id.get(p.get("shot_id"))
        if s is None:
            continue
        cqs.append(float(s.cinematic_quality or 0.0))
        tqs.append(float(s.technical_quality or 0.0))
        sharps.append(float(getattr(s, "sharpness", 0.0) or 0.0))
    if not cqs:
        return {"n_picks": len(picks)}
    return {
        "n_picks": len(picks),
        "mean_cinematic": round(sum(cqs) / len(cqs), 4),
        "mean_technical": round(sum(tqs) / len(tqs), 4),
        "mean_sharpness": round(sum(sharps) / len(sharps), 4),
        "cq_ge_062": sum(1 for c in cqs if c >= 0.62),
    }


def main() -> int:
    V9_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
    os.environ["WEDDING_V3_VISUAL_BOOST"] = "1"
    import wedding_v3.story as story_mod
    import wedding_v3.titles as titles_mod
    import wedding_v3.critic as critic_mod
    import wedding_v3.cinematic as cine_mod
    import wedding_v3.ranking as ranking_mod

    story_mod.PACE_HOLD_FLOOR = True
    titles_mod.TITLE_CARDS = True
    critic_mod.TITLE_CARDS = True
    cine_mod.TITLE_CARDS = True
    ranking_mod.VISUAL_BOOST = True

    print("=== V9 recovery render (variety-safe visual boost) ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V9",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        append_experiment_log(f"V9_visual_quality recovery FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V9_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    visual_stats = _plan_visual_stats(run_dir)
    eval_result = evaluate_run(run_dir, V8_BEST)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v9.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V9_visual_quality",
                hypothesis="Variety-safe visual boost recovery vs V8 8.60",
                configuration={"tag": TAG, "visual_boost": True, "variant": "v2"},
                status="running",
            )
            lab_db.finish_experiment(
                eid,
                score=score,
                runtime=float(run_result.get("runtime") or 0.0),
                result=f"KEEP vs V8 {V8_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V9_visual_quality",
                score,
                promoted,
                notes=f"v2 recovery KEEP delta={eval_result.get('delta')}",
                parent="V8_tears_reaction",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V9_visual_quality",
        "variant": "variety_safe_visual_boost_v2",
        "status": "completed",
        "hypothesis": (
            "Soft CQ floors + stronger same-video penalty lift visual without "
            "hard pool filtering that caused consecutive source repeats"
        ),
        "v8_baseline": V8_BEST,
        "v9_prior": V9_PRIOR,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v8": eval_result.get("delta"),
        "delta_vs_v9_prior": round(score - V9_PRIOR, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "visual_stats": visual_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V9_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V9_visual_quality recovery (v2) completed.",
                f"run_dir={run_dir}",
                f"visual_stats={visual_stats}",
                f"best_score={score} (V8 {V8_BEST}; prior V9 {V9_PRIOR})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V9_visual_quality"
    state.current_version = "V9_visual_quality"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V9_visual_quality"
        state.best_score = score
        state.last_strategy = "KEEP V9v2 visual; next: continuity_color"
        fails = [f for f in (state.failed_experiments or []) if f != "V9_visual_quality"]
        state.failed_experiments = fails
        state.next_tasks = [
            {
                "title": "V10_continuity_color",
                "hypothesis": "Color/continuity matching reduces stock-footage feeling",
                "priority": 1.0,
            },
            {
                "title": "V10_pacing_polish",
                "hypothesis": "Fine-tune hold lengths on high-CQ shots for pacing>7.5",
                "priority": 0.7,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V9_visual_quality" not in fails:
            fails.append("V9_visual_quality")
        state.failed_experiments = fails
        state.best_version = "V8_tears_reaction"
        state.best_score = V8_BEST
        state.last_strategy = "REJECT V9v2 visual; keep V8; next: continuity_color"
        state.next_tasks = [
            {
                "title": "V10_continuity_color",
                "hypothesis": "Color/continuity matching reduces stock-footage feeling",
                "priority": 1.0,
            },
            {
                "title": "V10_emotion_peak_polish",
                "hypothesis": "Hold peak emotion shots longer without chopping music sync",
                "priority": 0.8,
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
    jobs = [j for j in jobs if j.get("id") != "V9_visual_quality"]
    jobs.append(
        {
            "id": "V9_visual_quality",
            "script": "autolab/run_v9_recovery.py",
            "status": "done",
            "priority": 6,
            "hypothesis": "Variety-safe visual boost; prior v1 REJECT 8.44 vs 8.60",
            "depends_on": "V8_tears_reaction",
            "returncode": 0 if verdict == "KEEP" else 1,
            "score": score,
            "verdict": verdict,
            "note": f"v1={V9_PRIOR}; v2 recovery",
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": f"V9_visual_quality v2 {verdict} {score:.2f} vs V8 {V8_BEST} (v1={V9_PRIOR})",
        "best_version": state.best_version,
        "best_score": state.best_score,
        "renders_executed": True,
    }
    (ROOT / "autolab" / "results" / "BLOCKER.json").write_text(
        json.dumps(blocker, indent=2), encoding="utf-8"
    )

    print(json.dumps(eval_data, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
