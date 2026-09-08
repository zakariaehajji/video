"""One-shot runner for V14_peak_hold_soft experiment.

Hypothesis: Milder peak linger (+0.25s on top-3 emotion climaxes only), without
V11's aggressive variance-steal or duration-weighted critic, raises emotional
impact / pacing over V10 without the V11 no-gain / score-inflation path.

Compares against V10 best (8.69). Never overwrites BEST_v10 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V8 tears cues, V10 color continuity.
Does NOT enable V9 VISUAL_BOOST, V11 PEAK_HOLD, V12 MUSIC_SECTION_ROLES, V13 VISUAL_SOFT.
Critic PEAK_HOLD stays OFF (honest per-shot emotion, no duration weight).
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

V14_DIR = ROOT / "Output" / "autolab" / "V14"
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_peak_hold_soft"


def _peak_hold_stats(run_dir: Path) -> dict:
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
    holds = [
        p
        for p in picks
        if "peak-emotion-hold-soft" in (p.get("reasons") or [])
        or "peak-emotion-hold" in (p.get("reasons") or [])
    ]
    durs = [float(p.get("dur") or 0) for p in picks]
    peak_durs = [float(p.get("dur") or 0) for p in peaks] or [0.0]
    peak_emos = [float(p.get("emotion") or 0) for p in peaks] or [0.0]
    return {
        "n_picks": len(picks),
        "n_peaks": len(peaks),
        "n_peak_holds": len(holds),
        "mean_dur": round(sum(durs) / len(durs), 4),
        "peak_mean_dur": round(sum(peak_durs) / len(peak_durs), 4),
        "peak_mean_emotion": round(sum(peak_emos) / len(peak_emos), 4),
        "hold_mean_dur": round(
            sum(float(p.get("dur") or 0) for p in holds) / max(1, len(holds)), 4
        )
        if holds
        else 0.0,
        "hold_reasons": [
            r
            for p in holds
            for r in (p.get("reasons") or [])
            if "peak-emotion-hold" in r
        ],
    }


def _assert_wedding_pool() -> None:
    """Refuse single-source/whatsapp pools — V10 baseline needs multi-clip wedding footage."""
    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    videos = {str(x.get("video") or "") for x in data}
    stems = {Path(v).stem.lower() for v in videos}
    if len(videos) < 8 or any("whatsapp" in s for s in stems):
        raise RuntimeError(
            f"Corrupt/non-wedding shot pool ({len(data)} shots, {len(videos)} videos). "
            "Restore from wedding_* caches before running V14."
        )


def main() -> int:
    V14_DIR.mkdir(parents=True, exist_ok=True)
    _assert_wedding_pool()

    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
    os.environ["WEDDING_V3_COLOR_CONTINUITY"] = "1"
    os.environ["WEDDING_V3_COLOR_MATCH"] = "1"
    os.environ["WEDDING_V3_PEAK_HOLD_SOFT"] = "1"
    os.environ.pop("WEDDING_V3_PEAK_HOLD", None)
    os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
    os.environ.pop("WEDDING_V3_VISUAL_SOFT", None)
    os.environ.pop("WEDDING_V3_MUSIC_SECTION_ROLES", None)

    import wedding_v3.story as story_mod
    import wedding_v3.titles as titles_mod
    import wedding_v3.critic as critic_mod
    import wedding_v3.cinematic as cine_mod
    import wedding_v3.ranking as ranking_mod

    story_mod.PACE_HOLD_FLOOR = True
    story_mod.PEAK_HOLD = False  # V11 story peak rewrite OFF — isolate soft ranking polish
    titles_mod.TITLE_CARDS = True
    critic_mod.TITLE_CARDS = True
    critic_mod.COLOR_CONTINUITY = True
    critic_mod.PEAK_HOLD = False  # honest critic: no duration-weighted emotion
    critic_mod.MUSIC_SECTION_ROLES = False
    cine_mod.TITLE_CARDS = True
    cine_mod.COLOR_MATCH = True
    ranking_mod.COLOR_CONTINUITY = True
    ranking_mod.PEAK_HOLD = False
    ranking_mod.PEAK_HOLD_SOFT = True
    ranking_mod.VISUAL_BOOST = False
    ranking_mod.VISUAL_SOFT = False
    ranking_mod.MUSIC_SECTION_ROLES = False

    print("=== V14_peak_hold_soft render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V14",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V14_peak_hold_soft",
            "status": "failed",
            "error": err,
            "v10_baseline": V10_BEST,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V14_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V14_peak_hold_soft FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V14_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    peak_stats = _peak_hold_stats(run_dir)
    eval_result = evaluate_run(run_dir, V10_BEST)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v14.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V14_peak_hold_soft",
                hypothesis=(
                    "Milder peak linger (+0.25s top-3 only) without duration-weight critic"
                ),
                configuration={
                    "tag": TAG,
                    "peak_hold_soft": True,
                    "peak_hold": False,
                    "pace_hold": True,
                    "color_continuity": True,
                    "critic_peak_hold": False,
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
                "V14_peak_hold_soft",
                score,
                promoted,
                notes=f"peak_hold_soft KEEP delta={eval_result.get('delta')}",
                parent="V10_continuity_color",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V14_peak_hold_soft",
        "status": "completed",
        "hypothesis": (
            "Milder peak linger (+0.25s top-3 only) without duration-weight critic"
        ),
        "v10_baseline": V10_BEST,
        "v8_baseline": V8_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v10": eval_result.get("delta"),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "peak_stats": peak_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V14_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V14_peak_hold_soft completed.",
                f"run_dir={run_dir}",
                f"peak={peak_stats}",
                f"best_score={score} (V10 baseline {V10_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V14_peak_hold_soft"
    state.current_version = "V14_peak_hold_soft"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V14_peak_hold_soft"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V14_peak_hold_soft"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V14 peak_hold_soft; next: emotion_model_refresh"
        state.next_tasks = [
            {
                "title": "V15_emotion_model_refresh",
                "hypothesis": "Improve real emotion cues beyond smile/kiss/hug heuristics",
                "priority": 1.0,
            },
            {
                "title": "V15_ceremony_narrative",
                "hypothesis": "Stronger ceremony arc (vows→rings→kiss→exit) lifts story coherence",
                "priority": 0.75,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V14_peak_hold_soft" not in fails:
            fails.append("V14_peak_hold_soft")
        state.failed_experiments = fails
        state.best_version = "V10_continuity_color"
        state.best_score = V10_BEST
        state.last_strategy = "REJECT V14 peak_hold_soft; keep V10; next: emotion_model_refresh"
        state.next_tasks = [
            {
                "title": "V15_emotion_model_refresh",
                "hypothesis": "Improve real emotion cues beyond smile/kiss/hug heuristics",
                "priority": 1.0,
            },
            {
                "title": "V15_reaction_cutaways",
                "hypothesis": "Insert guest/family reaction cutaways on vow/peak beats",
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
    jobs = [j for j in jobs if j.get("id") != "V14_peak_hold_soft"]
    jobs.append(
        {
            "id": "V14_peak_hold_soft",
            "script": "autolab/run_v14_peak_hold_soft.py",
            "status": "done",
            "priority": 11,
            "hypothesis": (
                "Milder peak linger (+0.25s top-3 only) without duration-weight critic"
            ),
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
        "note": f"V14_peak_hold_soft {verdict} {score:.2f} vs V10 {V10_BEST}",
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
