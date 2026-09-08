"""One-shot runner for V24_continuity_soft_v2 experiment.

Hypothesis: V10 COLOR_CONTINUITY is aggressive (65% palette blend, +0.05 weight)
and can over-constrain shot selection on the V21 stack. A milder continuity mode
that mainly punishes harsh adjacent LAB jumps + hard consecutive-source skip
(V9 failure) should lift continuity/visual coherence without starving emotion
or repeating sources.

Compares against V21 best (8.84). Never overwrites BEST_v21 / BEST_v20 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V10 color match + continuity base, V15 MediaPipe,
V20 peak faces, V21 reaction cutaways v2. Does NOT enable V9 VISUAL_BOOST,
V11/V14 PEAK_HOLD, V19/V22 PACE_BREATHE, V23 KISS_HOLD.
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
os.environ["WEDDING_V3_CONTINUITY_SOFT_V2"] = "1"
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
os.environ.pop("WEDDING_V3_PACE_BREATHE_V2", None)
os.environ.pop("WEDDING_V3_KISS_HOLD", None)

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V24_DIR = ROOT / "Output" / "autolab" / "V24"
V21_BEST = 8.84
V20_BEST = 8.82
V15_BEST = 8.73
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_continuity_soft_v2"


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
            "Restore from wedding_* caches before running V24."
        )


def _color_stats(run_dir: Path) -> dict:
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
    consec = sum(1 for a, b in zip(shots, shots[1:]) if a.video == b.video)
    soft_hits = sum(
        1
        for p in picks
        if any(
            r in (p.get("reasons") or [])
            for r in (
                "color-match-soft",
                "contsoftv2-hard-consec-skip",
                "contsoftv2-harsh-jump-skip",
                "cool-palette-soft",
                "warm-palette-soft",
                "bookend-exposure-soft",
            )
        )
    )
    return {
        "n_picks": len(shots),
        "mean_adj_color_dist": round(sum(dists) / len(dists), 4),
        "harsh_jumps_ge_055": sum(1 for d in dists if d >= 0.55),
        "max_adj_color_dist": round(max(dists), 4),
        "mean_color_b": round(sum(float(s.color_b) for s in shots) / len(shots), 3),
        "consecutive_same_source": consec,
        "unique_sources": len({s.video for s in shots}),
        "soft_reason_hits": soft_hits,
        "color_match_reasons": sum(
            1
            for p in picks
            if "color-match" in (p.get("reasons") or [])
            or "color-match-soft" in (p.get("reasons") or [])
        ),
        "color_jump_reasons": sum(
            1 for p in picks if "color-jump" in (p.get("reasons") or [])
        ),
    }


def main() -> int:
    V24_DIR.mkdir(parents=True, exist_ok=True)

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
    story_mod.PACE_BREATHE = False
    if hasattr(story_mod, "PACE_BREATHE_V2"):
        story_mod.PACE_BREATHE_V2 = False
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
    cine_mod.CONTINUITY_SOFT_V2 = True
    ranking_mod.COLOR_CONTINUITY = True
    ranking_mod.CONTINUITY_SOFT_V2 = True
    ranking_mod.PEAK_HOLD = False
    ranking_mod.PEAK_HOLD_SOFT = False
    ranking_mod.PACE_BREATHE = False
    ranking_mod.PACE_BREATHE_V2 = False
    ranking_mod.VISUAL_BOOST = False
    ranking_mod.VISUAL_SOFT = False
    if hasattr(ranking_mod, "VISUAL_SOFT_V2"):
        ranking_mod.VISUAL_SOFT_V2 = False
    ranking_mod.MUSIC_SECTION_ROLES = False
    ranking_mod.CEREMONY_NARRATIVE = False
    ranking_mod.PEAK_PAYOFF_FACES = True
    ranking_mod.REACTION_CUTAWAYS = True
    ranking_mod.REACTION_CUTAWAYS_V2 = True
    if hasattr(ranking_mod, "KISS_HOLD"):
        ranking_mod.KISS_HOLD = False

    pool_stats = _rebuild_wedding_pool()
    _assert_wedding_pool()
    print(json.dumps({"pool_stats": pool_stats}, indent=2), flush=True)

    print("=== V24_continuity_soft_v2 render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V24",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V24_continuity_soft_v2",
            "status": "failed",
            "error": err,
            "v21_baseline": V21_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V24_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V24_continuity_soft_v2 FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V24_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    color_stats = _color_stats(run_dir)
    eval_result = evaluate_run(run_dir, V21_BEST)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = (
        json.loads(leaderboard_path.read_text(encoding="utf-8"))
        if leaderboard_path.exists()
        else {}
    )
    score = float(eval_result.get("score") or 0.0)
    # Require real improvement + no V9 consecutive-source regression.
    consec_ok = int(color_stats.get("consecutive_same_source") or 0) == 0
    verdict = (
        "KEEP"
        if eval_result.get("better_than_best") and consec_ok
        else "REJECT"
    )
    if eval_result.get("better_than_best") and not consec_ok:
        print(
            "REJECT despite higher score: consecutive_same_source>0 (V9 failure mode)",
            flush=True,
        )
    best = leaderboard.get("best") or {}
    best_src = best.get("path")
    promoted = None
    if verdict == "KEEP" and best_src and Path(best_src).exists():
        dest = ROOT / "Output" / "autolab" / "BEST_v24.mp4"
        shutil.copy2(best_src, dest)
        rolling = ROOT / "Output" / "autolab" / "BEST_current.mp4"
        shutil.copy2(best_src, rolling)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V24_continuity_soft_v2",
                hypothesis=(
                    "Milder adjacent color continuity + harsh-jump/consec guards "
                    "without V9 source-repeat"
                ),
                configuration={
                    "tag": TAG,
                    "continuity_soft_v2": True,
                    "color_continuity": True,
                    "color_match": True,
                    "reaction_cutaways_v2": True,
                    "peak_payoff_faces": True,
                    "pace_hold": True,
                    "emotion_mediapipe": True,
                    "title_cards": True,
                },
                status="running",
            )
            lab_db.finish_experiment(
                eid,
                score=score,
                runtime=float(run_result.get("runtime") or 0.0),
                result=f"KEEP vs V21 {V21_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V24_continuity_soft_v2",
                score,
                promoted,
                notes=f"continuity_soft_v2 KEEP delta={eval_result.get('delta')}",
                parent="V21_reaction_cutaways_v2",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V24_continuity_soft_v2",
        "status": "completed",
        "hypothesis": (
            "Milder adjacent color continuity without V9 source-repeat "
            "(on top of V21 face+reaction grammar)"
        ),
        "v21_baseline": V21_BEST,
        "v20_baseline": V20_BEST,
        "v15_baseline": V15_BEST,
        "v10_baseline": V10_BEST,
        "v8_baseline": V8_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v21": eval_result.get("delta"),
        "delta_vs_v20": round(score - V20_BEST, 3),
        "delta_vs_v15": round(score - V15_BEST, 3),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "consec_ok": consec_ok,
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
    (V24_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V24_continuity_soft_v2 completed.",
                f"run_dir={run_dir}",
                f"color={color_stats}",
                f"best_score={score} (V21 baseline {V21_BEST})",
                f"verdict={verdict}",
                f"consec_ok={consec_ok}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V24_continuity_soft_v2"
    state.current_version = "V24_continuity_soft_v2"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V24_continuity_soft_v2"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V24_continuity_soft_v2"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V24 continuity_soft_v2; next: kiss_ensure_swap"
        state.next_tasks = [
            {
                "title": "V25_kiss_ensure_swap",
                "hypothesis": "Force top pool kiss into peak if hold alone is insufficient",
                "priority": 1.0,
            },
            {
                "title": "V25_visual_cq_bridge",
                "hypothesis": "Mild CQ preference under soft continuity without V9 collapse",
                "priority": 0.8,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V24_continuity_soft_v2" not in fails:
            fails.append("V24_continuity_soft_v2")
        state.failed_experiments = fails
        state.best_version = "V21_reaction_cutaways_v2"
        state.best_score = V21_BEST
        state.last_strategy = "REJECT V24 continuity_soft_v2; keep V21; next: kiss_ensure_swap"
        state.next_tasks = [
            {
                "title": "V25_kiss_ensure_swap",
                "hypothesis": "Force top pool kiss into peak if hold alone is insufficient",
                "priority": 1.0,
            },
            {
                "title": "V25_visual_cq_soft_v3",
                "hypothesis": "Attack visual_quality~6.3 with CQ nudge under V21 stack",
                "priority": 0.85,
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
    jobs = [j for j in jobs if j.get("id") != "V24_continuity_soft_v2"]
    jobs.append(
        {
            "id": "V24_continuity_soft_v2",
            "script": "autolab/run_v24_continuity_soft_v2.py",
            "status": "done",
            "priority": 20,
            "hypothesis": "Milder adjacent color continuity without V9 source-repeat",
            "depends_on": "V21_reaction_cutaways_v2",
            "returncode": 0 if verdict == "KEEP" else 1,
            "score": score,
            "verdict": verdict,
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": f"V24_continuity_soft_v2 {verdict} {score:.2f} vs V21 {V21_BEST}",
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
