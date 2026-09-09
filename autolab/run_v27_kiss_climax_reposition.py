"""One-shot runner for V27_kiss_climax_reposition experiment.

Hypothesis: V21's best kiss (wedding_36171_000 ~0.43) sits mid-peak (idx 16 of
9–24) rather than in the late-peak climax window. V25 injects unused pool kisses
into late slots and REJECTED (8.81 vs 8.84). Reorder the *existing* strongest
kiss into late climax without new pool swaps — pure ceremony payoff timing.

Compares against V21 best (8.84). Never overwrites BEST_v21 / BEST_v20 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V10 color, V15 MediaPipe, V20 peak faces, V21
reaction cutaways v2. Does NOT enable V23 KISS_HOLD, V25 KISS_ENSURE_SWAP,
V11/V14 PEAK_HOLD, V19/V22 PACE_BREATHE, V24 CONTINUITY_SOFT_V2, V26 VISUAL_SOFT_V3.
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
os.environ["WEDDING_V3_KISS_CLIMAX_REPOSITION"] = "1"
os.environ.pop("WEDDING_V3_PEAK_HOLD", None)
os.environ.pop("WEDDING_V3_PEAK_HOLD_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT_V2", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT_V3", None)
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

V27_DIR = ROOT / "Output" / "autolab" / "V27"
V21_BEST = 8.84
V20_BEST = 8.82
V15_BEST = 8.73
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_kiss_climax_reposition"


def _rebuild_wedding_pool() -> dict:
    import wedding_v3.shots as shots_mod

    shots_mod.EMOTION_MEDIAPIPE = True
    shots_mod.CACHE_SCHEMA = "v6_mediapipe_emotion"
    vid_dir = ROOT / "resource" / "video" / "wedding_web"
    print(f"=== Load wedding_web pool ({shots_mod.CACHE_SCHEMA}) ===", flush=True)
    shots = shots_mod.build_pool(vid_dir, force=False)
    true_rx = 0
    kiss_ge = 0
    for s in shots:
        r = float(getattr(s, "reaction", 0.0) or 0.0)
        k = float(getattr(s, "kiss", 0.0) or 0.0)
        h = float(getattr(s, "hug", 0.0) or 0.0)
        faces = int(getattr(s, "faces", 0) or 0)
        if faces >= 1 and r >= 0.48 and k < 0.35 and h < 0.50:
            true_rx += 1
        if k >= 0.40:
            kiss_ge += 1
    emos = [float(s.emotion_score) for s in shots]
    kisses = [float(getattr(s, "kiss", 0.0) or 0.0) for s in shots]
    return {
        "n_shots": len(shots),
        "n_videos": len({s.video for s in shots}),
        "cache_schema": shots_mod.CACHE_SCHEMA,
        "true_reaction_cutaways": true_rx,
        "kiss_ge_040": kiss_ge,
        "kiss_max": round(max(kisses) if kisses else 0.0, 4),
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
            "Restore from wedding_* caches before running V27."
        )


def _kiss_reposition_stats(run_dir: Path) -> dict:
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

    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    kiss_by_id: dict[str, float] = {}
    if pool_path.exists():
        for x in json.loads(pool_path.read_text(encoding="utf-8")):
            sid = str(x.get("id") or "")
            kiss_by_id[sid] = float(x.get("kiss") or 0.0)

    peaks = [p for p in picks if p.get("peak") or p.get("section") == "peak"]
    peak_idxs = [
        i for i, p in enumerate(picks) if p.get("peak") or p.get("section") == "peak"
    ]
    if len(peak_idxs) >= 6:
        late_start = (2 * len(peak_idxs)) // 3
        climax_slots = set(peak_idxs[late_start:-1])
    else:
        climax_slots = set(peak_idxs[len(peak_idxs) // 2 : -1] or peak_idxs[1:-1])

    moved = [p for p in picks if "kiss-climax-reposition" in (p.get("reasons") or [])]
    already = [p for p in picks if "kiss-climax-reposition-ok" in (p.get("reasons") or [])]
    displaced = [p for p in picks if "kiss-climax-displaced" in (p.get("reasons") or [])]
    ensure_tags = [
        p
        for p in picks
        if any(
            t in (p.get("reasons") or [])
            for t in ("kiss-ensure-swap", "kiss-ensure-top", "kiss-ensure-fallback")
        )
    ]

    durs = [float(p.get("dur") or 0) for p in picks]
    peak_durs = [float(p.get("dur") or 0) for p in peaks] or [0.0]
    peak_emos = [float(p.get("emotion") or 0) for p in peaks] or [0.0]
    peak_kisses = [kiss_by_id.get(str(p.get("shot_id") or ""), 0.0) for p in peaks]

    best_kiss_idx = None
    best_kiss_val = -1.0
    best_kiss_id = None
    for i, p in enumerate(picks):
        k = kiss_by_id.get(str(p.get("shot_id") or ""), 0.0)
        if k > best_kiss_val:
            best_kiss_val = k
            best_kiss_idx = i
            best_kiss_id = p.get("shot_id")

    mean = sum(durs) / len(durs)
    var = sum((d - mean) ** 2 for d in durs) / len(durs)
    return {
        "n_picks": len(picks),
        "n_peaks": len(peaks),
        "n_kiss_repositions": len(moved),
        "n_kiss_already_late": len(already),
        "n_displaced": len(displaced),
        "n_ensure_tags": len(ensure_tags),
        "best_kiss_idx": best_kiss_idx,
        "best_kiss_id": best_kiss_id,
        "best_kiss": round(best_kiss_val, 4),
        "best_kiss_in_late_climax": bool(
            best_kiss_idx is not None and best_kiss_idx in climax_slots
        ),
        "late_climax_slots": sorted(climax_slots),
        "mean_dur": round(mean, 4),
        "dur_var": round(var, 4),
        "peak_mean_dur": round(sum(peak_durs) / len(peak_durs), 4),
        "peak_mean_emotion": round(sum(peak_emos) / len(peak_emos), 4),
        "peak_max_kiss": round(max(peak_kisses) if peak_kisses else 0.0, 4),
        "moved_shot_ids": [p.get("shot_id") for p in moved],
        "micro_cuts_lt_1": sum(1 for d in durs if d < 1.0),
    }


def main() -> int:
    V27_DIR.mkdir(parents=True, exist_ok=True)

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
    ranking_mod.COLOR_CONTINUITY = True
    ranking_mod.PEAK_HOLD = False
    ranking_mod.PEAK_HOLD_SOFT = False
    ranking_mod.PACE_BREATHE = False
    ranking_mod.PACE_BREATHE_V2 = False
    ranking_mod.VISUAL_BOOST = False
    ranking_mod.VISUAL_SOFT = False
    if hasattr(ranking_mod, "VISUAL_SOFT_V2"):
        ranking_mod.VISUAL_SOFT_V2 = False
    if hasattr(ranking_mod, "VISUAL_SOFT_V3"):
        ranking_mod.VISUAL_SOFT_V3 = False
    if hasattr(ranking_mod, "CONTINUITY_SOFT_V2"):
        ranking_mod.CONTINUITY_SOFT_V2 = False
    ranking_mod.MUSIC_SECTION_ROLES = False
    ranking_mod.CEREMONY_NARRATIVE = False
    ranking_mod.PEAK_PAYOFF_FACES = True
    ranking_mod.REACTION_CUTAWAYS = True
    ranking_mod.REACTION_CUTAWAYS_V2 = True
    ranking_mod.KISS_HOLD = False
    ranking_mod.KISS_ENSURE_SWAP = False
    ranking_mod.KISS_CLIMAX_REPOSITION = True

    pool_stats = _rebuild_wedding_pool()
    _assert_wedding_pool()
    print(json.dumps({"pool_stats": pool_stats}, indent=2), flush=True)

    print("=== V27_kiss_climax_reposition render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V27",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V27_kiss_climax_reposition",
            "status": "failed",
            "error": err,
            "v21_baseline": V21_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V27_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V27_kiss_climax_reposition FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V27_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    kiss_stats = _kiss_reposition_stats(run_dir)
    # Mechanism must fire: either moved into late climax, or already late-tagged.
    repo_ok = (
        int(kiss_stats.get("n_kiss_repositions") or 0) >= 1
        or int(kiss_stats.get("n_kiss_already_late") or 0) >= 1
        or bool(kiss_stats.get("best_kiss_in_late_climax"))
    )
    # Must not have used V25 ensure path.
    no_ensure = int(kiss_stats.get("n_ensure_tags") or 0) == 0
    eval_result = evaluate_run(run_dir, V21_BEST)
    leaderboard_path = run_dir / "leaderboard.json"
    leaderboard = (
        json.loads(leaderboard_path.read_text(encoding="utf-8"))
        if leaderboard_path.exists()
        else {}
    )
    score = float(eval_result.get("score") or 0.0)
    mechanism_ok = repo_ok and no_ensure
    verdict = "KEEP" if eval_result.get("better_than_best") and mechanism_ok else "REJECT"
    if not mechanism_ok and eval_result.get("better_than_best"):
        print(
            "WARN: score up but reposition mechanism miss / ensure tags present — REJECT",
            flush=True,
        )
    best = leaderboard.get("best") or {}
    best_src = best.get("path")
    promoted = None
    if verdict == "KEEP" and best_src and Path(best_src).exists():
        dest = ROOT / "Output" / "autolab" / "BEST_v27.mp4"
        shutil.copy2(best_src, dest)
        rolling = ROOT / "Output" / "autolab" / "BEST_current.mp4"
        shutil.copy2(best_src, rolling)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V27_kiss_climax_reposition",
                hypothesis=(
                    "Move existing best kiss to late-peak climax without new swaps"
                ),
                configuration={
                    "tag": TAG,
                    "kiss_climax_reposition": True,
                    "kiss_ensure_swap": False,
                    "kiss_hold": False,
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
                result=f"KEEP vs V21 {V21_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V27_kiss_climax_reposition",
                score,
                promoted,
                notes=f"kiss_climax_reposition KEEP delta={eval_result.get('delta')}",
                parent="V21_reaction_cutaways_v2",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V27_kiss_climax_reposition",
        "status": "completed",
        "hypothesis": (
            "Move existing best kiss to late-peak climax without new swaps "
            "(V25 unused-pool ensure REJECT 8.81)"
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
        "mechanism_ok": mechanism_ok,
        "repo_ok": repo_ok,
        "no_ensure": no_ensure,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "pool_stats": pool_stats,
        "kiss_stats": kiss_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V27_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V27_kiss_climax_reposition completed.",
                f"run_dir={run_dir}",
                f"kiss={kiss_stats}",
                f"best_score={score} (V21 baseline {V21_BEST})",
                f"verdict={verdict}",
                f"mechanism_ok={mechanism_ok}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V27_kiss_climax_reposition"
    state.current_version = "V27_kiss_climax_reposition"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V27_kiss_climax_reposition"
        state.best_score = score
        fails = [
            f for f in (state.failed_experiments or []) if f != "V27_kiss_climax_reposition"
        ]
        state.failed_experiments = fails
        state.last_strategy = (
            "KEEP V27 kiss_climax_reposition; next: intro_detail_cq_pool"
        )
        state.next_tasks = [
            {
                "title": "V28_intro_detail_cq_pool",
                "hypothesis": (
                    "Seed higher-CQ detail/wide bookend alternatives without "
                    "role-flex portraits"
                ),
                "priority": 1.0,
            },
            {
                "title": "V28_reaction_portrait_bias",
                "hypothesis": "Bias forced cutaways to single-face tear portraits only",
                "priority": 0.7,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V27_kiss_climax_reposition" not in fails:
            fails.append("V27_kiss_climax_reposition")
        state.failed_experiments = fails
        state.best_version = "V21_reaction_cutaways_v2"
        state.best_score = V21_BEST
        state.last_strategy = (
            "REJECT V27 kiss_climax_reposition; keep V21; next: intro_detail_cq_pool"
        )
        state.next_tasks = [
            {
                "title": "V28_intro_detail_cq_pool",
                "hypothesis": (
                    "Seed higher-CQ detail/wide bookend alternatives without "
                    "role-flex portraits"
                ),
                "priority": 1.0,
            },
            {
                "title": "V28_peak_kiss_hold_after_reposition",
                "hypothesis": (
                    "If reposition mechanism fires but score flat, add mild hold "
                    "only on late-climax kiss"
                ),
                "priority": 0.65,
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
    jobs = [j for j in jobs if j.get("id") != "V27_kiss_climax_reposition"]
    jobs.append(
        {
            "id": "V27_kiss_climax_reposition",
            "script": "autolab/run_v27_kiss_climax_reposition.py",
            "status": "done",
            "priority": 22,
            "hypothesis": "Move existing best kiss to late-peak climax without new swaps",
            "depends_on": "V21_reaction_cutaways_v2",
            "returncode": 0 if verdict == "KEEP" else 1,
            "score": score,
            "verdict": verdict,
            "mechanism_ok": mechanism_ok,
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            f"V27_kiss_climax_reposition {verdict} {score:.2f} vs V21 {V21_BEST} "
            f"mechanism_ok={mechanism_ok}"
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
