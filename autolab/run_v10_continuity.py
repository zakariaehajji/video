"""One-shot runner for V10_continuity_color experiment.

Hypothesis: Palette-aware shot chaining + mild film-look grading reduces
stock-footage color jumps while keeping V5 pace-hold, V7 titles, V8 tears.

Compares against V8 best (8.60). Never overwrites BEST_v8 / BEST_v3.
Does NOT enable V9 VISUAL_BOOST (already REJECTED).
"""

from __future__ import annotations

import json
import os
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

V10_DIR = ROOT / "Output" / "autolab" / "V10"
V8_BEST = 8.60
V9_BEST = 8.50  # rejected
V3 = 8.15
TAG = "autolab_continuity_color"


def _rebuild_shot_pool() -> dict:
    from wedding_v3.shots import CACHE_SCHEMA, build_pool, color_distance, load_pool

    vid_dir = ROOT / "resource" / "video" / "wedding_web"
    print(f"=== Force rebuild shot pool ({CACHE_SCHEMA}) ===", flush=True)
    shots = build_pool(vid_dir, force=True)
    # Pairwise mean color distance sample (first 40 shots) for diagnostics
    sample = shots[:40]
    dists = []
    for i in range(1, len(sample)):
        dists.append(color_distance(sample[i - 1], sample[i]))
    warm = [float(s.color_b) for s in shots]
    stats = {
        "n_shots": len(shots),
        "cache_schema": CACHE_SCHEMA,
        "mean_color_l": round(sum(float(s.color_l) for s in shots) / max(1, len(shots)), 3),
        "mean_color_b": round(sum(warm) / max(1, len(warm)), 3),
        "warm_ge_6": sum(1 for w in warm if w >= 6.0),
        "cool_lt_m4": sum(1 for w in warm if w < -4.0),
        "sample_adj_mean_dist": round(sum(dists) / max(1, len(dists)), 4) if dists else 0.0,
    }
    print(json.dumps(stats, indent=2), flush=True)
    # Ensure pool.json is loadable
    _ = load_pool()
    return stats


def _plan_color_stats(run_dir: Path) -> dict:
    from wedding_v3.shots import color_distance, load_pool

    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    by_id = {}
    if pool_path.exists():
        try:
            by_id = {s.id: s for s in load_pool(pool_path)}
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
    shots = []
    for p in picks:
        s = by_id.get(p.get("shot_id"))
        if s is not None:
            shots.append(s)
    if len(shots) < 2:
        return {"n_picks": len(picks)}
    dists = [color_distance(a, b) for a, b in zip(shots, shots[1:])]
    return {
        "n_picks": len(shots),
        "mean_adj_color_dist": round(sum(dists) / len(dists), 4),
        "harsh_jumps_ge_055": sum(1 for d in dists if d >= 0.55),
        "mean_color_b": round(sum(float(s.color_b) for s in shots) / len(shots), 3),
        "color_match_reasons": sum(
            1
            for p in picks
            if "color-match" in (p.get("reasons") or [])
        ),
    }


def main() -> int:
    V10_DIR.mkdir(parents=True, exist_ok=True)

    # Keep V5/V7/V8 gates; add V10 color continuity + film-look match.
    # Do NOT enable VISUAL_BOOST (V9 REJECT).
    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
    os.environ["WEDDING_V3_COLOR_CONTINUITY"] = "1"
    os.environ["WEDDING_V3_COLOR_MATCH"] = "1"
    os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)

    import wedding_v3.story as story_mod
    import wedding_v3.titles as titles_mod
    import wedding_v3.critic as critic_mod
    import wedding_v3.cinematic as cine_mod
    import wedding_v3.ranking as ranking_mod

    story_mod.PACE_HOLD_FLOOR = True
    titles_mod.TITLE_CARDS = True
    critic_mod.TITLE_CARDS = True
    critic_mod.COLOR_CONTINUITY = True
    cine_mod.TITLE_CARDS = True
    cine_mod.COLOR_MATCH = True
    ranking_mod.COLOR_CONTINUITY = True
    ranking_mod.VISUAL_BOOST = False

    pool_stats = _rebuild_shot_pool()

    print("=== V10_continuity_color render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V10",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V10_continuity_color",
            "status": "failed",
            "error": err,
            "v8_baseline": V8_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V10_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V10_continuity_color FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V10_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    color_stats = _plan_color_stats(run_dir)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v10.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V10_continuity_color",
                hypothesis=(
                    "Color/continuity matching reduces stock-footage feeling"
                ),
                configuration={
                    "tag": TAG,
                    "cache_schema": pool_stats.get("cache_schema"),
                    "color_match": True,
                },
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
                "V10_continuity_color",
                score,
                promoted,
                notes=f"continuity_color KEEP delta={eval_result.get('delta')}",
                parent="V8_tears_reaction",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V10_continuity_color",
        "status": "completed",
        "hypothesis": (
            "Palette-aware shot chaining + film-look grading reduces "
            "stock-footage color jumps"
        ),
        "v8_baseline": V8_BEST,
        "v9_rejected": V9_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v8": eval_result.get("delta"),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "pool_stats": pool_stats,
        "color_stats": color_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V10_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V10_continuity_color completed.",
                f"run_dir={run_dir}",
                f"pool={pool_stats}",
                f"color={color_stats}",
                f"best_score={score} (V8 baseline {V8_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V10_continuity_color"
    state.current_version = "V10_continuity_color"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V10_continuity_color"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V10_continuity_color"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V10 continuity_color; next: emotion_peak_polish"
        state.next_tasks = [
            {
                "title": "V11_emotion_peak_polish",
                "hypothesis": "Hold peak emotion shots longer without chopping music sync",
                "priority": 1.0,
            },
            {
                "title": "V11_music_section_roles",
                "hypothesis": "Tighter music-section→story-role mapping lifts music_sync",
                "priority": 0.7,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V10_continuity_color" not in fails:
            fails.append("V10_continuity_color")
        state.failed_experiments = fails
        state.best_version = "V8_tears_reaction"
        state.best_score = V8_BEST
        state.last_strategy = "REJECT V10 continuity; keep V8; next: emotion_peak_polish"
        state.next_tasks = [
            {
                "title": "V10_emotion_peak_polish",
                "hypothesis": "Hold peak emotion shots longer without chopping music sync",
                "priority": 1.0,
            },
            {
                "title": "V10_continuity_soft_grade_only",
                "hypothesis": "Film-look grade alone without ranking color bias",
                "priority": 0.6,
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
    jobs = [j for j in jobs if j.get("id") != "V10_continuity_color"]
    jobs.append(
        {
            "id": "V10_continuity_color",
            "script": "autolab/run_v10_continuity.py",
            "status": "done",
            "priority": 7,
            "hypothesis": "Color/continuity matching reduces stock-footage feeling",
            "depends_on": "V8_tears_reaction",
            "returncode": 0 if verdict == "KEEP" else 1,
            "score": score,
            "verdict": verdict,
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": f"V10_continuity_color {verdict} {score:.2f} vs V8 {V8_BEST}",
        "best_version": state.best_version,
        "best_score": state.best_score,
        "renders_executed": True,
    }
    (ROOT / "autolab" / "results" / "BLOCKER.json").write_text(
        json.dumps(blocker, indent=2), encoding="utf-8"
    )

    print(json.dumps(eval_data, indent=2), flush=True)
    return 0 if verdict == "KEEP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
