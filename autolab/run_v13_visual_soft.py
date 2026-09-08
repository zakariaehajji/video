"""One-shot runner for V13_visual_quality_soft experiment.

Hypothesis: Mild CQ/sharpness preference stacked on V10 color continuity lifts
visual_quality (V10=6.32) without V9's consecutive-source / variety collapse.

Compares against V10 best (8.69). Never overwrites BEST_v10 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V8 tears cues, V10 color continuity.
Does NOT enable V9 VISUAL_BOOST, V11 PEAK_HOLD, or V12 MUSIC_SECTION_ROLES.
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

V13_DIR = ROOT / "Output" / "autolab" / "V13"
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_visual_quality_soft"


def _assert_wedding_pool() -> None:
    """Refuse single-source/whatsapp pools — V10 baseline needs multi-clip wedding footage."""
    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    videos = {str(x.get("video") or "") for x in data}
    stems = {Path(v).stem.lower() for v in videos}
    if len(videos) < 8 or any("whatsapp" in s for s in stems):
        raise RuntimeError(
            f"Corrupt/non-wedding shot pool ({len(data)} shots, {len(videos)} videos). "
            "Restore from wedding_* caches before running V13."
        )


def _plan_visual_stats(run_dir: Path) -> dict:
    from wedding_v3.shots import load_pool

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
    cqs, tqs, sharps = [], [], []
    soft_hits = 0
    consec = 0
    videos = []
    for p in picks:
        reasons = p.get("reasons") or []
        if any(
            r in reasons
            for r in ("soft-high-cq", "soft-low-cq", "soft-sharp-tech", "soft-bookend-cq", "soft-consec-guard")
        ):
            soft_hits += 1
        s = by_id.get(p.get("shot_id"))
        vid = str(p.get("video") or (getattr(s, "video", "") if s else ""))
        if videos and vid and vid == videos[-1]:
            consec += 1
        if vid:
            videos.append(vid)
        if s is None:
            continue
        cqs.append(float(s.cinematic_quality or 0.0))
        tqs.append(float(s.technical_quality or 0.0))
        sharps.append(float(getattr(s, "sharpness", 0.0) or 0.0))
    if not cqs:
        return {"n_picks": len(picks), "consecutive_same_source": consec, "soft_reason_hits": soft_hits}
    return {
        "n_picks": len(picks),
        "mean_cinematic": round(sum(cqs) / len(cqs), 4),
        "mean_technical": round(sum(tqs) / len(tqs), 4),
        "mean_sharpness": round(sum(sharps) / len(sharps), 4),
        "cq_ge_062": sum(1 for c in cqs if c >= 0.62),
        "cq_ge_066": sum(1 for c in cqs if c >= 0.66),
        "unique_sources": len(set(videos)),
        "consecutive_same_source": consec,
        "soft_reason_hits": soft_hits,
    }


def main() -> int:
    V13_DIR.mkdir(parents=True, exist_ok=True)
    _assert_wedding_pool()

    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
    os.environ["WEDDING_V3_COLOR_CONTINUITY"] = "1"
    os.environ["WEDDING_V3_COLOR_MATCH"] = "1"
    os.environ["WEDDING_V3_VISUAL_SOFT"] = "1"
    os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
    os.environ.pop("WEDDING_V3_PEAK_HOLD", None)
    os.environ.pop("WEDDING_V3_MUSIC_SECTION_ROLES", None)

    import wedding_v3.story as story_mod
    import wedding_v3.titles as titles_mod
    import wedding_v3.critic as critic_mod
    import wedding_v3.cinematic as cine_mod
    import wedding_v3.ranking as ranking_mod

    story_mod.PACE_HOLD_FLOOR = True
    titles_mod.TITLE_CARDS = True
    critic_mod.TITLE_CARDS = True
    critic_mod.COLOR_CONTINUITY = True
    critic_mod.PEAK_HOLD = False
    critic_mod.MUSIC_SECTION_ROLES = False
    cine_mod.TITLE_CARDS = True
    cine_mod.COLOR_MATCH = True
    ranking_mod.COLOR_CONTINUITY = True
    ranking_mod.VISUAL_SOFT = True
    ranking_mod.VISUAL_BOOST = False
    ranking_mod.PEAK_HOLD = False
    ranking_mod.MUSIC_SECTION_ROLES = False

    print("=== V13_visual_quality_soft render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V13",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V13_visual_quality_soft",
            "status": "failed",
            "error": err,
            "v10_baseline": V10_BEST,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V13_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V13_visual_quality_soft FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V13_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    visual_stats = _plan_visual_stats(run_dir)
    eval_result = evaluate_run(run_dir, V10_BEST)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = (
        json.loads(leaderboard_path.read_text(encoding="utf-8"))
        if leaderboard_path.exists()
        else {}
    )
    score = float(eval_result.get("score") or 0.0)
    # Reject if consecutive-source failure returns (V9 failure mode).
    consec = int(visual_stats.get("consecutive_same_source") or 0)
    problems = list(eval_result.get("problems") or [])
    if consec > 0 and "same source repeated consecutively" not in problems:
        # Critic already flags this; keep local guard for soft experiment.
        pass
    hard_fail = consec >= 2 or "same source repeated consecutively" in problems
    better = bool(eval_result.get("better_than_best")) and not hard_fail
    verdict = "KEEP" if better else "REJECT"
    best = leaderboard.get("best") or {}
    best_src = best.get("path")
    promoted = None
    if verdict == "KEEP" and best_src and Path(best_src).exists():
        dest = ROOT / "Output" / "autolab" / "BEST_v13.mp4"
        shutil.copy2(best_src, dest)
        # Also refresh rolling best pointer without touching BEST_v10 archive.
        rolling = ROOT / "Output" / "autolab" / "BEST_current.mp4"
        shutil.copy2(best_src, rolling)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V13_visual_quality_soft",
                hypothesis=(
                    "Soft CQ preference without V9 consecutive-source failure"
                ),
                configuration={
                    "tag": TAG,
                    "visual_soft": True,
                    "color_continuity": True,
                },
                status="running",
            )
            lab_db.finish_experiment(
                eid,
                score=score,
                runtime=float(run_result.get("runtime") or 0.0),
                result=f"KEEP vs V10 {V10_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V13_visual_quality_soft",
                score,
                promoted,
                notes=f"visual_soft KEEP delta={eval_result.get('delta')}",
                parent="V10_continuity_color",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V13_visual_quality_soft",
        "status": "completed",
        "hypothesis": (
            "Soft CQ preference on V10 continuity lifts visual without "
            "V9 consecutive-source failure"
        ),
        "v10_baseline": V10_BEST,
        "v8_baseline": V8_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v10": eval_result.get("delta"),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "hard_fail_consecutive": hard_fail,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "visual_stats": visual_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": problems,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V13_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V13_visual_quality_soft completed.",
                f"run_dir={run_dir}",
                f"visual_stats={visual_stats}",
                f"best_score={score} (V10 baseline {V10_BEST})",
                f"verdict={verdict}",
                f"problems={problems}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V13_visual_quality_soft"
    state.current_version = "V13_visual_quality_soft"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V13_visual_quality_soft"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V13_visual_quality_soft"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V13 visual_soft; next: peak_hold_soft or emotion detection"
        state.next_tasks = [
            {
                "title": "V14_peak_hold_soft",
                "hypothesis": "Milder peak linger (+0.25s top-3 only) without duration-weight critic",
                "priority": 1.0,
            },
            {
                "title": "V14_kiss_hug_threshold_tune",
                "hypothesis": "Retune kiss/hug thresholds for more true positives without false peaks",
                "priority": 0.75,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V13_visual_quality_soft" not in fails:
            fails.append("V13_visual_quality_soft")
        state.failed_experiments = fails
        state.best_version = "V10_continuity_color"
        state.best_score = V10_BEST
        state.last_strategy = "REJECT V13 visual_soft; keep V10; next: peak_hold_soft"
        state.next_tasks = [
            {
                "title": "V14_peak_hold_soft",
                "hypothesis": "Milder peak linger (+0.25s top-3 only) without duration-weight critic",
                "priority": 1.0,
            },
            {
                "title": "V14_emotion_model_refresh",
                "hypothesis": "Improve real emotion cues beyond smile/kiss/hug heuristics",
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
    jobs = [j for j in jobs if j.get("id") != "V13_visual_quality_soft"]
    jobs.append(
        {
            "id": "V13_visual_quality_soft",
            "script": "autolab/run_v13_visual_soft.py",
            "status": "done",
            "priority": 10,
            "hypothesis": "Soft CQ preference without V9 consecutive-source failure",
            "depends_on": "V10_continuity_color",
            "returncode": 0 if verdict == "KEEP" else 1,
            "score": score,
            "verdict": verdict,
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": f"V13_visual_quality_soft {verdict} {score:.2f} vs V10 {V10_BEST}",
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
