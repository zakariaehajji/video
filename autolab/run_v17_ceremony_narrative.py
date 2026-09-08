"""One-shot runner for V17_ceremony_narrative experiment.

Hypothesis: Stronger ceremony arc inside the musical peak
(vows → rings → kiss → exit) lifts story coherence and emotional payoff
versus V15's flatter couple/portrait/motion rotation.

Compares against V15 best (8.73). Never overwrites BEST_v15 / BEST_v10 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V10 color continuity, V15 MediaPipe emotion.
Does NOT enable V9 VISUAL_BOOST, V11/V14 PEAK_HOLD, V12 MUSIC_SECTION_ROLES,
V13 VISUAL_SOFT, or V16 REACTION_CUTAWAYS (rejected).
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
os.environ["WEDDING_V3_CEREMONY_NARRATIVE"] = "1"
os.environ.pop("WEDDING_V3_PEAK_HOLD", None)
os.environ.pop("WEDDING_V3_PEAK_HOLD_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT", None)
os.environ.pop("WEDDING_V3_MUSIC_SECTION_ROLES", None)
os.environ.pop("WEDDING_V3_REACTION_CUTAWAYS", None)

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V17_DIR = ROOT / "Output" / "autolab" / "V17"
V15_BEST = 8.73
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_ceremony_narrative"


def _assert_wedding_pool() -> None:
    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    videos = {str(x.get("video") or "") for x in data}
    stems = {Path(v).stem.lower() for v in videos}
    if len(videos) < 8 or any("whatsapp" in s for s in stems):
        raise RuntimeError(
            f"Corrupt/non-wedding shot pool ({len(data)} shots, {len(videos)} videos). "
            "Restore from wedding_* caches before running V17."
        )


def _ceremony_plan_stats(run_dir: Path) -> dict:
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
    if not picks:
        return {}

    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    pool = {s["id"]: s for s in json.loads(pool_path.read_text(encoding="utf-8"))}

    peak_picks = [p for p in picks if p.get("peak") or p.get("section") == "peak"]
    n_peak = len(peak_picks)

    def _phase(i: int) -> str:
        if n_peak <= 1:
            return "kiss"
        frac = i / float(max(1, n_peak - 1))
        if frac <= 0.20:
            return "vow"
        if frac <= 0.38:
            return "ring"
        if frac <= 0.78:
            return "kiss"
        return "exit"

    phase_hits = {"vow": 0, "ring": 0, "kiss": 0, "exit": 0}
    swap_n = 0
    reason_n = 0
    kiss_in_kiss_phase = 0
    kiss_early = 0
    for i, p in enumerate(peak_picks):
        reasons = p.get("reasons") or []
        if "ceremony-narrative-swap" in reasons:
            swap_n += 1
        if any(str(r).startswith("ceremony-") for r in reasons):
            reason_n += 1
        phase = _phase(i)
        shot = pool.get(p.get("shot_id") or "", {})
        kiss = float(shot.get("kiss") or 0)
        hug = float(shot.get("hug") or 0)
        tears = float(shot.get("tears") or 0)
        st = shot.get("shot_type") or p.get("role")
        if phase == "vow" and (tears >= 0.42 or st == "portrait"):
            phase_hits["vow"] += 1
        elif phase == "ring" and (st == "detail" or int(shot.get("faces") or 0) == 0):
            phase_hits["ring"] += 1
        elif phase == "kiss" and (kiss >= 0.35 or hug >= 0.50):
            phase_hits["kiss"] += 1
            kiss_in_kiss_phase += 1
        elif phase == "exit" and st in ("wide", "motion", "couple"):
            phase_hits["exit"] += 1
        if phase == "vow" and kiss >= 0.40:
            kiss_early += 1

    emos = [float(p.get("emotion") or 0) for p in picks]
    peak_emos = [float(p.get("emotion") or 0) for p in peak_picks] or [0.0]
    return {
        "n_picks": len(picks),
        "n_peaks": n_peak,
        "n_ceremony_swaps": swap_n,
        "n_ceremony_reason_picks": reason_n,
        "phase_hits": phase_hits,
        "kiss_in_kiss_phase": kiss_in_kiss_phase,
        "kiss_early_in_vow": kiss_early,
        "mean_emotion": round(sum(emos) / len(emos), 4),
        "peak_mean_emotion": round(sum(peak_emos) / len(peak_emos), 4),
        "peak_roles": [p.get("role") for p in peak_picks],
    }


def _pool_stats() -> dict:
    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    return {
        "n_shots": len(data),
        "kiss_ge_040": sum(1 for s in data if float(s.get("kiss") or 0) >= 0.40),
        "hug_ge_050": sum(1 for s in data if float(s.get("hug") or 0) >= 0.50),
        "detail": sum(1 for s in data if s.get("shot_type") == "detail"),
        "tears_ge_042": sum(1 for s in data if float(s.get("tears") or 0) >= 0.42),
        "cache_schema": "v6_mediapipe_emotion",
    }


def main() -> int:
    V17_DIR.mkdir(parents=True, exist_ok=True)
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
    story_mod.CEREMONY_NARRATIVE = True
    story_mod.MUSIC_SECTION_ROLES = False
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
    ranking_mod.REACTION_CUTAWAYS = False
    ranking_mod.CEREMONY_NARRATIVE = True

    pool_stats = _pool_stats()
    print(json.dumps({"pool_stats": pool_stats}, indent=2), flush=True)

    print("=== V17_ceremony_narrative render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V17",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V17_ceremony_narrative",
            "status": "failed",
            "error": err,
            "v15_baseline": V15_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V17_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V17_ceremony_narrative FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V17_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    ceremony_stats = _ceremony_plan_stats(run_dir)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v17.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V17_ceremony_narrative",
                hypothesis=(
                    "Stronger ceremony arc (vows→rings→kiss→exit) lifts story coherence"
                ),
                configuration={
                    "tag": TAG,
                    "ceremony_narrative": True,
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
                "V17_ceremony_narrative",
                score,
                promoted,
                notes=f"ceremony_narrative KEEP delta={eval_result.get('delta')}",
                parent="V15_emotion_model_refresh",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V17_ceremony_narrative",
        "status": "completed",
        "hypothesis": (
            "Stronger ceremony arc (vows→rings→kiss→exit) lifts story coherence "
            "and emotional payoff vs flat peak rotation"
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
        "ceremony_stats": ceremony_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V17_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V17_ceremony_narrative completed.",
                f"run_dir={run_dir}",
                f"pool={pool_stats}",
                f"ceremony={ceremony_stats}",
                f"best_score={score} (V15 baseline {V15_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V17_ceremony_narrative"
    state.current_version = "V17_ceremony_narrative"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V17_ceremony_narrative"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V17_ceremony_narrative"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V17 ceremony_narrative; next: visual_quality_soft_v2"
        state.next_tasks = [
            {
                "title": "V18_visual_quality_soft_v2",
                "hypothesis": "Mild CQ preference with consecutive-source guard lifts visual_quality ~6.3",
                "priority": 1.0,
            },
            {
                "title": "V18_kiss_temporal_nms",
                "hypothesis": "Temporal max-pool kiss/hug reduces single-frame false positives",
                "priority": 0.7,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V17_ceremony_narrative" not in fails:
            fails.append("V17_ceremony_narrative")
        state.failed_experiments = fails
        state.best_version = "V15_emotion_model_refresh"
        state.best_score = V15_BEST
        state.last_strategy = "REJECT V17 ceremony_narrative; keep V15; next: visual_quality_soft_v2"
        state.next_tasks = [
            {
                "title": "V18_visual_quality_soft_v2",
                "hypothesis": "Mild CQ preference with consecutive-source guard lifts visual_quality ~6.3",
                "priority": 1.0,
            },
            {
                "title": "V18_pacing_breathe",
                "hypothesis": "Slightly longer mid-peak holds reduce busy pacing without flattening emotion",
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
    jobs = [j for j in jobs if j.get("id") != "V17_ceremony_narrative"]
    jobs.append(
        {
            "id": "V17_ceremony_narrative",
            "script": "autolab/run_v17_ceremony_narrative.py",
            "status": "done",
            "priority": 14,
            "hypothesis": (
                "Stronger ceremony arc (vows→rings→kiss→exit) lifts story coherence"
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
        "note": f"V17_ceremony_narrative {verdict} {score:.2f} vs V15 {V15_BEST}",
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
