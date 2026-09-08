"""One-shot runner for V16_reaction_cutaways experiment.

Hypothesis: Soft reaction ranking labels fire on intimacy frames themselves.
Structural intercalation — after kiss/hug/tear couple peaks, force-swap the next
beat to a true guest/family reaction (high reaction, low kiss/hug) — raises
emotional impact via classic vow→reaction wedding grammar.

Compares against V15 best (8.73). Never overwrites BEST_v15 / BEST_v10 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V10 color continuity, V15 MediaPipe emotion.
Does NOT enable V9 VISUAL_BOOST, V11 PEAK_HOLD, V12 MUSIC_SECTION_ROLES,
V13 VISUAL_SOFT, V14 PEAK_HOLD_SOFT.
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
os.environ["WEDDING_V3_REACTION_CUTAWAYS"] = "1"
os.environ.pop("WEDDING_V3_PEAK_HOLD", None)
os.environ.pop("WEDDING_V3_PEAK_HOLD_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT", None)
os.environ.pop("WEDDING_V3_MUSIC_SECTION_ROLES", None)

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V16_DIR = ROOT / "Output" / "autolab" / "V16"
V15_BEST = 8.73
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_reaction_cutaways"


def _assert_wedding_pool() -> None:
    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    videos = {str(x.get("video") or "") for x in data}
    stems = {Path(v).stem.lower() for v in videos}
    if len(videos) < 8 or any("whatsapp" in s for s in stems):
        raise RuntimeError(
            f"Corrupt/non-wedding shot pool ({len(data)} shots, {len(videos)} videos). "
            "Restore from wedding_* caches before running V16."
        )


def _reaction_plan_stats(run_dir: Path) -> dict:
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
    forced = [
        p
        for p in picks
        if "reaction-cutaway-forced" in (p.get("reasons") or [])
    ]
    after = [
        p
        for p in picks
        if "reaction-after-intimacy" in (p.get("reasons") or [])
    ]
    rx_reasons = [
        p
        for p in picks
        if any(
            r in (p.get("reasons") or [])
            for r in ("reaction-cutaway", "reaction-cutaway-forced", "reaction-after-intimacy")
        )
    ]
    peaks = [p for p in picks if p.get("peak") or p.get("section") == "peak"]
    emos = [float(p.get("emotion") or 0) for p in picks]
    peak_emos = [float(p.get("emotion") or 0) for p in peaks] or [0.0]
    return {
        "n_picks": len(picks),
        "n_peaks": len(peaks),
        "n_forced_cutaways": len(forced),
        "n_after_intimacy": len(after),
        "n_reaction_reason_picks": len(rx_reasons),
        "mean_emotion": round(sum(emos) / len(emos), 4),
        "peak_mean_emotion": round(sum(peak_emos) / len(peak_emos), 4),
        "forced_shot_ids": [p.get("shot_id") for p in forced],
    }


def _pool_reaction_stats() -> dict:
    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    true_rx = 0
    for s in data:
        r = float(s.get("reaction") or 0)
        k = float(s.get("kiss") or 0)
        h = float(s.get("hug") or 0)
        faces = int(s.get("faces") or 0)
        if faces >= 1 and r >= 0.48 and k < 0.35 and h < 0.50:
            true_rx += 1
    return {
        "n_shots": len(data),
        "true_reaction_cutaways": true_rx,
        "cache_schema": "v6_mediapipe_emotion",
    }


def main() -> int:
    V16_DIR.mkdir(parents=True, exist_ok=True)
    _assert_wedding_pool()

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
    ranking_mod.VISUAL_BOOST = False
    ranking_mod.VISUAL_SOFT = False
    ranking_mod.MUSIC_SECTION_ROLES = False
    ranking_mod.REACTION_CUTAWAYS = True

    pool_stats = _pool_reaction_stats()
    print(json.dumps({"pool_stats": pool_stats}, indent=2), flush=True)

    print("=== V16_reaction_cutaways render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V16",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V16_reaction_cutaways",
            "status": "failed",
            "error": err,
            "v15_baseline": V15_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V16_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V16_reaction_cutaways FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V16_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    rx_stats = _reaction_plan_stats(run_dir)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v16.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V16_reaction_cutaways",
                hypothesis=(
                    "Force intercalate guest/family reaction cutaways after "
                    "intimacy peak payoffs"
                ),
                configuration={
                    "tag": TAG,
                    "reaction_cutaways": True,
                    "emotion_mediapipe": True,
                    "pace_hold": True,
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
                "V16_reaction_cutaways",
                score,
                promoted,
                notes=f"reaction_cutaways KEEP delta={eval_result.get('delta')}",
                parent="V15_emotion_model_refresh",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V16_reaction_cutaways",
        "status": "completed",
        "hypothesis": (
            "Force intercalate guest/family reaction cutaways after intimacy "
            "peak payoffs (vow→reaction grammar)"
        ),
        "v15_baseline": V15_BEST,
        "v10_baseline": V10_BEST,
        "v8_baseline": V8_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v15": eval_result.get("delta"),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "pool_stats": pool_stats,
        "reaction_stats": rx_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V16_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V16_reaction_cutaways completed.",
                f"run_dir={run_dir}",
                f"pool={pool_stats}",
                f"reaction={rx_stats}",
                f"best_score={score} (V15 baseline {V15_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V16_reaction_cutaways"
    state.current_version = "V16_reaction_cutaways"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V16_reaction_cutaways"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V16_reaction_cutaways"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V16 reaction_cutaways; next: ceremony_narrative"
        state.next_tasks = [
            {
                "title": "V17_ceremony_narrative",
                "hypothesis": "Stronger ceremony arc (vows→rings→kiss→exit) lifts story coherence",
                "priority": 1.0,
            },
            {
                "title": "V17_visual_quality_soft_v2",
                "hypothesis": "Mild CQ preference with consecutive-source guard lifts visual_quality ~6.3",
                "priority": 0.8,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V16_reaction_cutaways" not in fails:
            fails.append("V16_reaction_cutaways")
        state.failed_experiments = fails
        state.best_version = "V15_emotion_model_refresh"
        state.best_score = V15_BEST
        state.last_strategy = "REJECT V16 reaction_cutaways; keep V15; next: ceremony_narrative"
        state.next_tasks = [
            {
                "title": "V17_ceremony_narrative",
                "hypothesis": "Stronger ceremony arc (vows→rings→kiss→exit) lifts story coherence",
                "priority": 1.0,
            },
            {
                "title": "V17_reaction_threshold_tune",
                "hypothesis": "Tune true-reaction thresholds if forced swaps dilute peak emotion",
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
    jobs = [j for j in jobs if j.get("id") != "V16_reaction_cutaways"]
    jobs.append(
        {
            "id": "V16_reaction_cutaways",
            "script": "autolab/run_v16_reaction_cutaways.py",
            "status": "done",
            "priority": 13,
            "hypothesis": (
                "Force intercalate guest/family reaction cutaways after intimacy peaks"
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
        "note": f"V16_reaction_cutaways {verdict} {score:.2f} vs V15 {V15_BEST}",
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
