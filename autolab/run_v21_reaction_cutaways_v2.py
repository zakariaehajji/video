"""One-shot runner for V21_reaction_cutaways_v2 experiment.

Hypothesis: V16 scored slightly below V15 with n_forced_cutaways=0 (annotate-only).
On top of V20 peak-face protection, force 2–3 true guest/family reaction cutaways
after intimacy with softer triggers + emo floor so vow→reaction grammar actually
lands without diluting peak faces.

Compares against V20 best (8.82). Never overwrites BEST_v20 / BEST_v15 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V10 color, V15 MediaPipe emotion, V20 peak faces.
Does NOT enable V9/V13/V18 visual boosts, V11/V14 PEAK_HOLD, V12 roles,
V17 ceremony, or V19 pace_breathe.
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
os.environ["WEDDING_V3_PEAK_PAYOFF_FACES"] = "1"
os.environ["WEDDING_V3_REACTION_CUTAWAYS"] = "1"
os.environ["WEDDING_V3_REACTION_CUTAWAYS_V2"] = "1"
os.environ.pop("WEDDING_V3_PEAK_HOLD", None)
os.environ.pop("WEDDING_V3_PEAK_HOLD_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT_V2", None)
os.environ.pop("WEDDING_V3_MUSIC_SECTION_ROLES", None)
os.environ.pop("WEDDING_V3_CEREMONY_NARRATIVE", None)
os.environ.pop("WEDDING_V3_PACE_BREATHE", None)

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V21_DIR = ROOT / "Output" / "autolab" / "V21"
V20_BEST = 8.82
V15_BEST = 8.73
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_reaction_cutaways_v2"


def _rebuild_wedding_pool() -> dict:
    import wedding_v3.shots as shots_mod

    shots_mod.EMOTION_MEDIAPIPE = True
    shots_mod.CACHE_SCHEMA = "v6_mediapipe_emotion"
    vid_dir = ROOT / "resource" / "video" / "wedding_web"
    print(f"=== Load wedding_web pool ({shots_mod.CACHE_SCHEMA}) ===", flush=True)
    shots = shots_mod.build_pool(vid_dir, force=False)
    true_rx = 0
    for s in shots:
        r = float(getattr(s, "reaction", 0.0) or 0.0)
        k = float(getattr(s, "kiss", 0.0) or 0.0)
        h = float(getattr(s, "hug", 0.0) or 0.0)
        faces = int(getattr(s, "faces", 0) or 0)
        if faces >= 1 and r >= 0.48 and k < 0.35 and h < 0.50:
            true_rx += 1
    emos = [float(s.emotion_score) for s in shots]
    return {
        "n_shots": len(shots),
        "n_videos": len({s.video for s in shots}),
        "cache_schema": shots_mod.CACHE_SCHEMA,
        "true_reaction_cutaways": true_rx,
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
            "Restore from wedding_* caches before running V21."
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
    forced = [p for p in picks if "reaction-cutaway-forced" in (p.get("reasons") or [])]
    v2 = [p for p in picks if "reaction-cutaway-v2" in (p.get("reasons") or [])]
    after = [p for p in picks if "reaction-after-intimacy" in (p.get("reasons") or [])]
    peaks = [p for p in picks if p.get("peak") or p.get("section") == "peak"]
    emos = [float(p.get("emotion") or 0) for p in picks]
    peak_emos = [float(p.get("emotion") or 0) for p in peaks] or [0.0]
    return {
        "n_picks": len(picks),
        "n_peaks": len(peaks),
        "n_forced_cutaways": len(forced),
        "n_v2_tags": len(v2),
        "n_after_intimacy": len(after),
        "mean_emotion": round(sum(emos) / len(emos), 4),
        "peak_mean_emotion": round(sum(peak_emos) / len(peak_emos), 4),
        "forced_shot_ids": [p.get("shot_id") for p in forced],
    }


def main() -> int:
    V21_DIR.mkdir(parents=True, exist_ok=True)

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
    if hasattr(story_mod, "PACE_BREATHE"):
        story_mod.PACE_BREATHE = False
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
    ranking_mod.PACE_BREATHE = False
    ranking_mod.VISUAL_BOOST = False
    ranking_mod.VISUAL_SOFT = False
    if hasattr(ranking_mod, "VISUAL_SOFT_V2"):
        ranking_mod.VISUAL_SOFT_V2 = False
    ranking_mod.MUSIC_SECTION_ROLES = False
    ranking_mod.CEREMONY_NARRATIVE = False
    ranking_mod.PEAK_PAYOFF_FACES = True
    ranking_mod.REACTION_CUTAWAYS = True
    ranking_mod.REACTION_CUTAWAYS_V2 = True

    pool_stats = _rebuild_wedding_pool()
    _assert_wedding_pool()
    print(json.dumps({"pool_stats": pool_stats}, indent=2), flush=True)

    print("=== V21_reaction_cutaways_v2 render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V21",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V21_reaction_cutaways_v2",
            "status": "failed",
            "error": err,
            "v20_baseline": V20_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V21_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V21_reaction_cutaways_v2 FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V21_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    rx_stats = _reaction_plan_stats(run_dir)
    eval_result = evaluate_run(run_dir, V20_BEST)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = (
        json.loads(leaderboard_path.read_text(encoding="utf-8"))
        if leaderboard_path.exists()
        else {}
    )
    score = float(eval_result.get("score") or 0.0)
    n_forced = int(rx_stats.get("n_forced_cutaways") or 0)
    # V16 failure mode was zero-swap; require real intercalation evidence.
    # KEEP if better than V20 with >=2 forced, or clear gain (>=+0.02) with >=1 forced.
    delta = float(eval_result.get("delta") or (score - V20_BEST))
    forced_ok = n_forced >= 2 or (n_forced >= 1 and delta >= 0.02)
    better = bool(eval_result.get("better_than_best")) and forced_ok
    verdict = "KEEP" if better else "REJECT"
    best = leaderboard.get("best") or {}
    best_src = best.get("path")
    promoted = None
    if verdict == "KEEP" and best_src and Path(best_src).exists():
        dest = ROOT / "Output" / "autolab" / "BEST_v21.mp4"
        shutil.copy2(best_src, dest)
        rolling = ROOT / "Output" / "autolab" / "BEST_current.mp4"
        shutil.copy2(best_src, rolling)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V21_reaction_cutaways_v2",
                hypothesis=(
                    "Force 2–3 true reaction cutaways after intimacy without V16 zero-swap"
                ),
                configuration={
                    "tag": TAG,
                    "reaction_cutaways_v2": True,
                    "peak_payoff_faces": True,
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
                result=f"KEEP vs V20 {V20_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V21_reaction_cutaways_v2",
                score,
                promoted,
                notes=f"reaction_cutaways_v2 KEEP delta={eval_result.get('delta')}",
                parent="V20_peak_payoff_faces",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V21_reaction_cutaways_v2",
        "status": "completed",
        "hypothesis": (
            "Force 2–3 true reaction cutaways after intimacy without V16 zero-swap "
            "(on top of V20 peak faces)"
        ),
        "v20_baseline": V20_BEST,
        "v15_baseline": V15_BEST,
        "v10_baseline": V10_BEST,
        "v8_baseline": V8_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v20": eval_result.get("delta"),
        "delta_vs_v15": round(score - V15_BEST, 3),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "forced_ok": forced_ok,
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
    (V21_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V21_reaction_cutaways_v2 completed.",
                f"run_dir={run_dir}",
                f"pool={pool_stats}",
                f"reaction={rx_stats}",
                f"best_score={score} (V20 baseline {V20_BEST})",
                f"verdict={verdict}",
                f"forced_ok={forced_ok}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V21_reaction_cutaways_v2"
    state.current_version = "V21_reaction_cutaways_v2"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V21_reaction_cutaways_v2"
        state.best_score = score
        fails = list(state.failed_experiments or [])
        fails = [f for f in fails if f != "V21_reaction_cutaways_v2"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V21 reaction_cutaways_v2; next: pacing_breathe_v2"
        state.next_tasks = [
            {
                "title": "V22_pacing_breathe_v2",
                "hypothesis": "Milder breathe on top of face-protected + reaction grammar",
                "priority": 1.0,
            },
            {
                "title": "V22_kiss_hold_polish",
                "hypothesis": "Hold strongest kiss climax longer without busy mid-peak spray",
                "priority": 0.75,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V21_reaction_cutaways_v2" not in fails:
            fails.append("V21_reaction_cutaways_v2")
        state.failed_experiments = fails
        state.best_version = "V20_peak_payoff_faces"
        state.best_score = V20_BEST
        state.last_strategy = "REJECT V21 reaction_cutaways_v2; keep V20; next: pacing_breathe_v2"
        state.next_tasks = [
            {
                "title": "V22_pacing_breathe_v2",
                "hypothesis": "Milder breathe on top of face-protected peaks",
                "priority": 1.0,
            },
            {
                "title": "V22_reaction_portrait_bias",
                "hypothesis": "Bias forced cutaways to single-face tear portraits only",
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
    jobs = [j for j in jobs if j.get("id") != "V21_reaction_cutaways_v2"]
    jobs.append(
        {
            "id": "V21_reaction_cutaways_v2",
            "script": "autolab/run_v21_reaction_cutaways_v2.py",
            "status": "done",
            "priority": 17,
            "hypothesis": (
                "Force 2–3 true reaction cutaways after intimacy without V16 zero-swap"
            ),
            "depends_on": "V20_peak_payoff_faces",
            "returncode": 0 if verdict == "KEEP" else 1,
            "score": score,
            "verdict": verdict,
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": f"V21_reaction_cutaways_v2 {verdict} {score:.2f} vs V20 {V20_BEST}",
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
