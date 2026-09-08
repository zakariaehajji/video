"""One-shot runner for V26_visual_cq_soft_v3 experiment.

Hypothesis: V21 best is locked at visual_quality~6.32 because intro bookends keep
low-CQ detail/wide stock frames. V9/V13/V18 ranking nudges lifted CQ but hurt
overall. V26 surgically upgrades lowest-CQ intro/outro/verse picks AFTER V21
peak-face + reaction polish — never demote peaks/intimacy/reactions.

Compares against V21 best (8.84). Never overwrites BEST_v21 / BEST_v20 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V10 color, V15 MediaPipe, V20 peak faces, V21
reaction cutaways v2. Does NOT enable V18 VISUAL_SOFT_V2, V9 VISUAL_BOOST,
V23/V25 kiss gates, V22 breathe, V24 continuity soft.
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
os.environ["WEDDING_V3_VISUAL_SOFT_V3"] = "1"
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
os.environ.pop("WEDDING_V3_KISS_ENSURE_SWAP", None)
os.environ.pop("WEDDING_V3_CONTINUITY_SOFT_V2", None)

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V26_DIR = ROOT / "Output" / "autolab" / "V26"
V21_BEST = 8.84
V20_BEST = 8.82
V15_BEST = 8.73
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_visual_cq_soft_v3"


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
    cqs = [float(s.cinematic_quality or 0.0) for s in shots]
    return {
        "n_shots": len(shots),
        "n_videos": len({s.video for s in shots}),
        "cache_schema": shots_mod.CACHE_SCHEMA,
        "true_reaction_cutaways": true_rx,
        "mean_emotion": round(sum(emos) / max(1, len(emos)), 4),
        "emotion_max": round(max(emos) if emos else 0.0, 4),
        "mean_cinematic": round(sum(cqs) / max(1, len(cqs)), 4),
        "cq_ge_062": sum(1 for c in cqs if c >= 0.62),
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
            "Restore from wedding_* caches before running V26."
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
    if not plan_path.exists() and name.endswith("_iter"):
        plan_path = run_dir / "plans" / f"{name[:-5]}.json"
    if not plan_path.exists():
        return {}
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    picks = plan.get("picks") or []
    cqs, tqs, sharps, emos = [], [], [], []
    soft_hits = 0
    upgrades = 0
    role_flex = 0
    consec = 0
    videos = []
    soft_keys = (
        "softv3-high-cq",
        "softv3-low-cq",
        "softv3-bookend-boost",
        "softv3-peak-cq",
        "softv3-consec-guard",
        "softv3-hard-consec-skip",
        "softv3-cq-upgrade",
        "softv3-role-flex",
    )
    upgrade_ids = []
    for p in picks:
        reasons = p.get("reasons") or []
        if any(r in reasons for r in soft_keys):
            soft_hits += 1
        if "softv3-cq-upgrade" in reasons:
            upgrades += 1
            upgrade_ids.append(p.get("shot_id"))
        if "softv3-role-flex" in reasons:
            role_flex += 1
        s = by_id.get(p.get("shot_id"))
        vid = str(p.get("video") or (getattr(s, "video", "") if s else ""))
        if videos and vid and vid == videos[-1]:
            consec += 1
        if vid:
            videos.append(vid)
        emos.append(float(p.get("emotion") or 0.0))
        if s is None:
            continue
        cqs.append(float(s.cinematic_quality or 0.0))
        tqs.append(float(s.technical_quality or 0.0))
        sharps.append(float(getattr(s, "sharpness", 0.0) or 0.0))
    if not cqs:
        return {
            "n_picks": len(picks),
            "consecutive_same_source": consec,
            "soft_reason_hits": soft_hits,
            "n_cq_upgrades": upgrades,
            "n_role_flex": role_flex,
            "upgrade_shot_ids": upgrade_ids,
            "mean_emotion": round(sum(emos) / max(1, len(emos)), 4) if emos else None,
        }
    return {
        "n_picks": len(picks),
        "mean_cinematic": round(sum(cqs) / len(cqs), 4),
        "mean_technical": round(sum(tqs) / len(tqs), 4),
        "mean_sharpness": round(sum(sharps) / len(sharps), 4),
        "mean_emotion": round(sum(emos) / max(1, len(emos)), 4) if emos else None,
        "cq_ge_062": sum(1 for c in cqs if c >= 0.62),
        "cq_ge_066": sum(1 for c in cqs if c >= 0.66),
        "cq_min": round(min(cqs), 4),
        "unique_sources": len(set(videos)),
        "consecutive_same_source": consec,
        "soft_reason_hits": soft_hits,
        "n_cq_upgrades": upgrades,
        "n_role_flex": role_flex,
        "upgrade_shot_ids": upgrade_ids,
    }


def main() -> int:
    V26_DIR.mkdir(parents=True, exist_ok=True)

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
    if hasattr(ranking_mod, "PACE_BREATHE_V2"):
        ranking_mod.PACE_BREATHE_V2 = False
    ranking_mod.VISUAL_BOOST = False
    ranking_mod.VISUAL_SOFT = False
    if hasattr(ranking_mod, "VISUAL_SOFT_V2"):
        ranking_mod.VISUAL_SOFT_V2 = False
    ranking_mod.VISUAL_SOFT_V3 = True
    ranking_mod.MUSIC_SECTION_ROLES = False
    ranking_mod.CEREMONY_NARRATIVE = False
    ranking_mod.PEAK_PAYOFF_FACES = True
    ranking_mod.REACTION_CUTAWAYS = True
    ranking_mod.REACTION_CUTAWAYS_V2 = True
    if hasattr(ranking_mod, "KISS_HOLD"):
        ranking_mod.KISS_HOLD = False
    if hasattr(ranking_mod, "KISS_ENSURE_SWAP"):
        ranking_mod.KISS_ENSURE_SWAP = False
    if hasattr(ranking_mod, "CONTINUITY_SOFT_V2"):
        ranking_mod.CONTINUITY_SOFT_V2 = False

    pool_stats = _rebuild_wedding_pool()
    _assert_wedding_pool()
    print(json.dumps({"pool_stats": pool_stats}, indent=2), flush=True)

    print("=== V26_visual_cq_soft_v3 render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V26",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V26_visual_cq_soft_v3",
            "status": "failed",
            "error": err,
            "v21_baseline": V21_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V26_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V26_visual_cq_soft_v3 FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V26_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    visual_stats = _plan_visual_stats(run_dir)
    eval_result = evaluate_run(run_dir, V21_BEST)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = (
        json.loads(leaderboard_path.read_text(encoding="utf-8"))
        if leaderboard_path.exists()
        else {}
    )
    score = float(eval_result.get("score") or 0.0)
    consec = int(visual_stats.get("consecutive_same_source") or 0)
    upgrades = int(visual_stats.get("n_cq_upgrades") or 0)
    problems = list(eval_result.get("problems") or [])
    hard_fail = consec >= 2 or "same source repeated consecutively" in problems
    # Require evidence the soft polish actually fired (else not a real CQ experiment).
    polish_ok = upgrades >= 1 or int(visual_stats.get("soft_reason_hits") or 0) >= 3
    better = bool(eval_result.get("better_than_best")) and not hard_fail
    verdict = "KEEP" if better and polish_ok else "REJECT"
    if better and not polish_ok:
        problems = list(problems) + ["visual_soft_v3 polish did not fire"]
    best = leaderboard.get("best") or {}
    best_src = best.get("path")
    promoted = None
    if verdict == "KEEP" and best_src and Path(best_src).exists():
        dest = ROOT / "Output" / "autolab" / "BEST_v26.mp4"
        shutil.copy2(best_src, dest)
        rolling = ROOT / "Output" / "autolab" / "BEST_current.mp4"
        shutil.copy2(best_src, rolling)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V26_visual_cq_soft_v3",
                hypothesis=(
                    "Bookend CQ upgrades under V21 stack lift visual_quality~6.3 "
                    "without peak demotion"
                ),
                configuration={
                    "tag": TAG,
                    "visual_soft_v3": True,
                    "peak_payoff_faces": True,
                    "reaction_cutaways_v2": True,
                    "emotion_mediapipe": True,
                    "color_continuity": True,
                    "pace_hold": True,
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
                "V26_visual_cq_soft_v3",
                score,
                promoted,
                notes=f"visual_cq_soft_v3 KEEP delta={eval_result.get('delta')}",
                parent="V21_reaction_cutaways_v2",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    critique = eval_result.get("critique") or {}
    eval_data = {
        "experiment": "V26_visual_cq_soft_v3",
        "status": "completed",
        "hypothesis": (
            "Attack visual_quality~6.3 with bookend CQ upgrades under V21 stack "
            "(no peak demotion)"
        ),
        "v21_baseline": V21_BEST,
        "v20_baseline": V20_BEST,
        "v15_baseline": V15_BEST,
        "v10_baseline": V10_BEST,
        "v8_baseline": V8_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v21": round(score - V21_BEST, 3),
        "delta_vs_v20": round(score - V20_BEST, 3),
        "delta_vs_v15": round(score - V15_BEST, 3),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "hard_fail_consecutive": hard_fail,
        "polish_ok": polish_ok,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "pool_stats": pool_stats,
        "visual_stats": visual_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": critique,
        "problems": problems,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V26_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V26_visual_cq_soft_v3 completed.",
                f"run_dir={run_dir}",
                f"visual_stats={visual_stats}",
                f"best_score={score} (V21 baseline {V21_BEST})",
                f"verdict={verdict}",
                f"polish_ok={polish_ok}",
                f"problems={problems}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V26_visual_cq_soft_v3"
    state.current_version = "V26_visual_cq_soft_v3"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V26_visual_cq_soft_v3"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V26_visual_cq_soft_v3"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V26 visual_cq_soft_v3; next: kiss_climax_reposition"
        state.next_tasks = [
            {
                "title": "V27_kiss_climax_reposition",
                "hypothesis": "Move existing best kiss to late-peak climax without new swaps",
                "priority": 1.0,
            },
            {
                "title": "V27_pacing_microcut_guard",
                "hypothesis": "Absorb sub-1.0s peak micro-cuts without flattening emotion holds",
                "priority": 0.7,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V26_visual_cq_soft_v3" not in fails:
            fails.append("V26_visual_cq_soft_v3")
        state.failed_experiments = fails
        state.best_version = "V21_reaction_cutaways_v2"
        state.best_score = V21_BEST
        state.last_strategy = "REJECT V26 visual_cq_soft_v3; keep V21; next: kiss_climax_reposition"
        state.next_tasks = [
            {
                "title": "V27_kiss_climax_reposition",
                "hypothesis": "Move existing best kiss to late-peak climax without new swaps",
                "priority": 1.0,
            },
            {
                "title": "V27_intro_detail_cq_pool",
                "hypothesis": "Seed higher-CQ detail/wide bookend alternatives without role-flex portraits",
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
    jobs = [j for j in jobs if j.get("id") != "V26_visual_cq_soft_v3"]
    jobs.append(
        {
            "id": "V26_visual_cq_soft_v3",
            "script": "autolab/run_v26_visual_cq_soft_v3.py",
            "status": "done",
            "priority": 26,
            "hypothesis": (
                "Attack visual_quality~6.3 with bookend CQ upgrades under V21 stack"
            ),
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
        "note": (
            f"V26_visual_cq_soft_v3 {verdict} {score:.2f} vs V21 {V21_BEST} "
            f"polish_ok={polish_ok}"
        ),
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
