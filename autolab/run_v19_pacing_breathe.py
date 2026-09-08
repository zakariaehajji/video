"""One-shot runner for V19_pacing_breathe experiment.

Hypothesis: Slightly longer mid-peak holds (fund from non-peak bookends; never
shrink peak shots) reduce busy pacing without flattening emotion — unlike
V11/V14 climax steals that shortened peak filler.

Compares against V15 best (8.73). Never overwrites BEST_v15 / BEST_v10 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V10 color continuity, V15 MediaPipe emotion.
Does NOT enable V9/V13/V18 visual boosts, V11/V14 PEAK_HOLD, V12 roles,
V16 reactions, or V17 ceremony narrative.
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

# Gates MUST be set before wedding_v3 imports that read env at module load.
os.environ["WEDDING_V3_EMOTION_MEDIAPIPE"] = "1"
os.environ["WEDDING_V3_PACE_HOLD"] = "1"
os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
os.environ["WEDDING_V3_COLOR_CONTINUITY"] = "1"
os.environ["WEDDING_V3_COLOR_MATCH"] = "1"
os.environ["WEDDING_V3_PACE_BREATHE"] = "1"
os.environ.pop("WEDDING_V3_PEAK_HOLD", None)
os.environ.pop("WEDDING_V3_PEAK_HOLD_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT_V2", None)
os.environ.pop("WEDDING_V3_MUSIC_SECTION_ROLES", None)
os.environ.pop("WEDDING_V3_REACTION_CUTAWAYS", None)
os.environ.pop("WEDDING_V3_CEREMONY_NARRATIVE", None)

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V19_DIR = ROOT / "Output" / "autolab" / "V19"
V15_BEST = 8.73
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_pacing_breathe"


def _rebuild_wedding_pool() -> dict:
    """Reuse wedding_web MediaPipe pool — comparable to V15."""
    import wedding_v3.shots as shots_mod

    shots_mod.EMOTION_MEDIAPIPE = True
    shots_mod.CACHE_SCHEMA = "v6_mediapipe_emotion"
    vid_dir = ROOT / "resource" / "video" / "wedding_web"
    print(f"=== Load wedding_web pool ({shots_mod.CACHE_SCHEMA}) ===", flush=True)
    shots = shots_mod.build_pool(vid_dir, force=False)
    emos = [float(s.emotion_score) for s in shots]
    return {
        "n_shots": len(shots),
        "n_videos": len({s.video for s in shots}),
        "cache_schema": shots_mod.CACHE_SCHEMA,
        "mean_emotion": round(sum(emos) / max(1, len(emos)), 4),
        "emotion_max": round(max(emos) if emos else 0.0, 4),
    }


def _assert_wedding_pool() -> None:
    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    videos = {str(x.get("video") or "") for x in data}
    stems = {Path(v).stem.lower() for v in videos}
    if len(videos) < 8 or any("whatsapp" in s for s in stems) or any(
        s.startswith("mixkit_") for s in stems
    ):
        raise RuntimeError(
            f"Corrupt/non-wedding shot pool ({len(data)} shots, {len(videos)} videos). "
            "Restore from wedding_* caches before running V19."
        )


def _pace_breathe_stats(run_dir: Path) -> dict:
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
    if not picks:
        return {}
    peaks = [p for p in picks if p.get("peak") or p.get("section") == "peak"]
    breathes = [p for p in picks if "pace-breathe" in (p.get("reasons") or [])]
    durs = [float(p.get("dur") or 0) for p in picks]
    peak_durs = [float(p.get("dur") or 0) for p in peaks] or [0.0]
    peak_emos = [float(p.get("emotion") or 0) for p in peaks] or [0.0]
    mean = sum(durs) / len(durs)
    var = sum((d - mean) ** 2 for d in durs) / len(durs)
    return {
        "n_picks": len(picks),
        "n_peaks": len(peaks),
        "n_breathes": len(breathes),
        "mean_dur": round(mean, 4),
        "dur_var": round(var, 4),
        "peak_mean_dur": round(sum(peak_durs) / len(peak_durs), 4),
        "peak_mean_emotion": round(sum(peak_emos) / len(peak_emos), 4),
        "breathe_mean_dur": round(
            sum(float(p.get("dur") or 0) for p in breathes) / max(1, len(breathes)), 4
        )
        if breathes
        else 0.0,
        "micro_cuts_lt_1": sum(1 for d in durs if d < 1.0),
    }


def main() -> int:
    V19_DIR.mkdir(parents=True, exist_ok=True)

    import wedding_v3.story as story_mod
    import wedding_v3.titles as titles_mod
    import wedding_v3.critic as critic_mod
    import wedding_v3.cinematic as cine_mod
    import wedding_v3.ranking as ranking_mod
    import wedding_v3.shots as shots_mod

    shots_mod.EMOTION_MEDIAPIPE = True
    shots_mod.CACHE_SCHEMA = "v6_mediapipe_emotion"
    story_mod.PACE_HOLD_FLOOR = True
    story_mod.PEAK_HOLD = False
    story_mod.PACE_BREATHE = True
    if hasattr(story_mod, "MUSIC_SECTION_ROLES"):
        story_mod.MUSIC_SECTION_ROLES = False
    if hasattr(story_mod, "CEREMONY_NARRATIVE"):
        story_mod.CEREMONY_NARRATIVE = False
    titles_mod.TITLE_CARDS = True
    critic_mod.TITLE_CARDS = True
    critic_mod.COLOR_CONTINUITY = True
    critic_mod.PEAK_HOLD = False
    critic_mod.MUSIC_SECTION_ROLES = False
    cine_mod.TITLE_CARDS = True
    cine_mod.COLOR_MATCH = True
    ranking_mod.COLOR_CONTINUITY = True
    ranking_mod.PEAK_HOLD = False
    ranking_mod.PEAK_HOLD_SOFT = False
    ranking_mod.PACE_BREATHE = True
    ranking_mod.VISUAL_BOOST = False
    ranking_mod.VISUAL_SOFT = False
    if hasattr(ranking_mod, "VISUAL_SOFT_V2"):
        ranking_mod.VISUAL_SOFT_V2 = False
    ranking_mod.MUSIC_SECTION_ROLES = False
    ranking_mod.REACTION_CUTAWAYS = False
    ranking_mod.CEREMONY_NARRATIVE = False

    pool_stats = _rebuild_wedding_pool()
    _assert_wedding_pool()
    print(json.dumps(pool_stats, indent=2), flush=True)

    print("=== V19_pacing_breathe render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V19",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V19_pacing_breathe",
            "status": "failed",
            "error": err,
            "v15_baseline": V15_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V19_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V19_pacing_breathe FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V19_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    pace_stats = _pace_breathe_stats(run_dir)
    eval_result = evaluate_run(run_dir, V15_BEST)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v19.mp4"
        shutil.copy2(best_src, dest)
        rolling = ROOT / "Output" / "autolab" / "BEST_current.mp4"
        shutil.copy2(best_src, rolling)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V19_pacing_breathe",
                hypothesis=(
                    "Slightly longer mid-peak holds reduce busy pacing "
                    "without flattening emotion"
                ),
                configuration={
                    "tag": TAG,
                    "pace_breathe": True,
                    "pace_hold": True,
                    "emotion_mediapipe": True,
                    "color_continuity": True,
                    "title_cards": True,
                },
                status="running",
            )
            lab_db.finish_experiment(
                eid,
                score=score,
                runtime=float(run_result.get("runtime") or 0.0),
                result=f"KEEP vs V15 {V15_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V19_pacing_breathe",
                score,
                promoted,
                notes=f"pace_breathe KEEP delta={eval_result.get('delta')}",
                parent="V15_emotion_model_refresh",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V19_pacing_breathe",
        "status": "completed",
        "hypothesis": (
            "Slightly longer mid-peak holds reduce busy pacing without flattening emotion"
        ),
        "v15_baseline": V15_BEST,
        "v10_baseline": V10_BEST,
        "v8_baseline": V8_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v15": eval_result.get("delta"),
        "delta_vs_v10": round(score - V10_BEST, 3),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "pool_stats": pool_stats,
        "pace_stats": pace_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V19_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V19_pacing_breathe completed.",
                f"run_dir={run_dir}",
                f"pace={pace_stats}",
                f"best_score={score} (V15 baseline {V15_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V19_pacing_breathe"
    state.current_version = "V19_pacing_breathe"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V19_pacing_breathe"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V19_pacing_breathe"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V19 pacing_breathe; next: peak_payoff_faces"
        state.next_tasks = [
            {
                "title": "V20_peak_payoff_faces",
                "hypothesis": "Require eye-contact/face on music peaks to fix weak visual payoff",
                "priority": 1.0,
            },
            {
                "title": "V20_visual_quality_soft_v3",
                "hypothesis": "Even milder CQ preference on top of breathing pacing",
                "priority": 0.7,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V19_pacing_breathe" not in fails:
            fails.append("V19_pacing_breathe")
        state.failed_experiments = fails
        state.best_version = "V15_emotion_model_refresh"
        state.best_score = V15_BEST
        state.last_strategy = "REJECT V19 pacing_breathe; keep V15; next: peak_payoff_faces"
        state.next_tasks = [
            {
                "title": "V20_peak_payoff_faces",
                "hypothesis": "Require eye-contact/face on music peaks to fix weak visual payoff",
                "priority": 1.0,
            },
            {
                "title": "V20_reaction_cutaways_v2",
                "hypothesis": "Force 2–3 true reaction cutaways after intimacy without V16 zero-swap",
                "priority": 0.75,
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
    jobs = [j for j in jobs if j.get("id") != "V19_pacing_breathe"]
    jobs.append(
        {
            "id": "V19_pacing_breathe",
            "script": "autolab/run_v19_pacing_breathe.py",
            "status": "done",
            "priority": 14,
            "hypothesis": (
                "Slightly longer mid-peak holds reduce busy pacing without flattening emotion"
            ),
            "depends_on": "V15_emotion_model_refresh",
            "returncode": 0 if verdict == "KEEP" else 1,
            "score": score,
            "verdict": verdict,
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": f"V19_pacing_breathe {verdict} {score:.2f} vs V15 {V15_BEST}",
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
