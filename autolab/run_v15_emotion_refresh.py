"""One-shot runner for V15_emotion_model_refresh experiment.

Hypothesis: MediaPipe Face Landmarker blendshapes (mouthSmile / frown / brow)
refresh real emotion cues beyond YuNet smile + proximity kiss/hug heuristics,
raising emotional impact while keeping the V10 continuity/color stack.

Compares against V10 best (8.69). Never overwrites BEST_v10 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V8 tears fields, V10 color continuity.
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

# Gate MUST be set before wedding_v3.shots import (CACHE_SCHEMA depends on it).
os.environ["WEDDING_V3_EMOTION_MEDIAPIPE"] = "1"
os.environ["WEDDING_V3_PACE_HOLD"] = "1"
os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
os.environ["WEDDING_V3_COLOR_CONTINUITY"] = "1"
os.environ["WEDDING_V3_COLOR_MATCH"] = "1"
os.environ.pop("WEDDING_V3_PEAK_HOLD", None)
os.environ.pop("WEDDING_V3_PEAK_HOLD_SOFT", None)
os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
os.environ.pop("WEDDING_V3_VISUAL_SOFT", None)
os.environ.pop("WEDDING_V3_MUSIC_SECTION_ROLES", None)

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V15_DIR = ROOT / "Output" / "autolab" / "V15"
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_emotion_model_refresh"


def _rebuild_shot_pool() -> dict:
    import wedding_v3.shots as shots_mod

    # Ensure module flags match this experiment even if previously imported.
    shots_mod.EMOTION_MEDIAPIPE = True
    shots_mod.CACHE_SCHEMA = "v6_mediapipe_emotion"

    vid_dir = ROOT / "resource" / "video" / "wedding_web"
    print(f"=== Force rebuild shot pool ({shots_mod.CACHE_SCHEMA}) ===", flush=True)
    shots = shots_mod.build_pool(vid_dir, force=True)
    smiles = [float(getattr(s, "smile", 0.0) or 0.0) for s in shots]
    emos = [float(s.emotion_score) for s in shots]
    kisses = [float(getattr(s, "kiss", 0.0) or 0.0) for s in shots]
    hugs = [float(getattr(s, "hug", 0.0) or 0.0) for s in shots]
    reactions = [float(getattr(s, "reaction", 0.0) or 0.0) for s in shots]
    tears = [float(getattr(s, "tears", 0.0) or 0.0) for s in shots]
    stats = {
        "n_shots": len(shots),
        "cache_schema": shots_mod.CACHE_SCHEMA,
        "emotion_mediapipe": True,
        "mean_emotion": round(sum(emos) / max(1, len(emos)), 4),
        "mean_smile": round(sum(smiles) / max(1, len(smiles)), 4),
        "smile_ge_035": sum(1 for s in smiles if s >= 0.35),
        "smile_ge_050": sum(1 for s in smiles if s >= 0.50),
        "kiss_ge_040": sum(1 for k in kisses if k >= 0.40),
        "hug_ge_050": sum(1 for h in hugs if h >= 0.50),
        "reaction_ge_050": sum(1 for r in reactions if r >= 0.50),
        "tears_ge_042": sum(1 for t in tears if t >= 0.42),
        "emotion_max": round(max(emos) if emos else 0.0, 4),
        "smile_max": round(max(smiles) if smiles else 0.0, 4),
        "kiss_max": round(max(kisses) if kisses else 0.0, 4),
        "hug_max": round(max(hugs) if hugs else 0.0, 4),
        "reaction_max": round(max(reactions) if reactions else 0.0, 4),
        "tears_max": round(max(tears) if tears else 0.0, 4),
    }
    print(json.dumps(stats, indent=2), flush=True)
    return stats


def _emotion_plan_stats(run_dir: Path) -> dict:
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
    emos = [float(p.get("emotion") or 0) for p in picks]
    peak_emos = [float(p.get("emotion") or 0) for p in peaks] or [0.0]
    smiles = [float(p.get("smile") or 0) for p in picks if p.get("smile") is not None]
    return {
        "n_picks": len(picks),
        "n_peaks": len(peaks),
        "mean_emotion": round(sum(emos) / len(emos), 4),
        "peak_mean_emotion": round(sum(peak_emos) / len(peak_emos), 4),
        "mean_smile": round(sum(smiles) / len(smiles), 4) if smiles else None,
        "emotion_reasons": sum(
            1
            for p in picks
            for r in (p.get("reasons") or [])
            if any(k in r for k in ("smile", "kiss", "hug", "tear", "reaction", "emotion"))
        ),
    }


def _assert_wedding_pool() -> None:
    pool_path = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
    data = json.loads(pool_path.read_text(encoding="utf-8"))
    videos = {str(x.get("video") or "") for x in data}
    stems = {Path(v).stem.lower() for v in videos}
    if len(videos) < 8 or any("whatsapp" in s for s in stems):
        raise RuntimeError(
            f"Corrupt/non-wedding shot pool ({len(data)} shots, {len(videos)} videos). "
            "Restore from wedding_* caches before running V15."
        )


def main() -> int:
    V15_DIR.mkdir(parents=True, exist_ok=True)

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

    pool_stats = _rebuild_shot_pool()
    _assert_wedding_pool()

    print("=== V15_emotion_model_refresh render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V15",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V15_emotion_model_refresh",
            "status": "failed",
            "error": err,
            "v10_baseline": V10_BEST,
            "pool_stats": pool_stats,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V15_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V15_emotion_model_refresh FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V15_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    emo_stats = _emotion_plan_stats(run_dir)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v15.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V15_emotion_model_refresh",
                hypothesis=(
                    "MediaPipe blendshape smile/solemn cues refresh emotion beyond "
                    "YuNet/proximity heuristics"
                ),
                configuration={
                    "tag": TAG,
                    "emotion_mediapipe": True,
                    "cache_schema": "v6_mediapipe_emotion",
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
                result=f"KEEP vs V10 {V10_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V15_emotion_model_refresh",
                score,
                promoted,
                notes=f"emotion_model_refresh KEEP delta={eval_result.get('delta')}",
                parent="V10_continuity_color",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V15_emotion_model_refresh",
        "status": "completed",
        "hypothesis": (
            "MediaPipe blendshape smile/solemn cues refresh emotion beyond "
            "YuNet/proximity heuristics"
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
        "pool_stats": pool_stats,
        "emotion_stats": emo_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V15_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V15_emotion_model_refresh completed.",
                f"run_dir={run_dir}",
                f"pool={pool_stats}",
                f"emotion={emo_stats}",
                f"best_score={score} (V10 baseline {V10_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V15_emotion_model_refresh"
    state.current_version = "V15_emotion_model_refresh"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V15_emotion_model_refresh"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V15_emotion_model_refresh"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V15 emotion_model_refresh; next: reaction_cutaways"
        state.next_tasks = [
            {
                "title": "V16_reaction_cutaways",
                "hypothesis": "Insert guest/family reaction cutaways on vow/peak beats",
                "priority": 1.0,
            },
            {
                "title": "V16_ceremony_narrative",
                "hypothesis": "Stronger ceremony arc (vows→rings→kiss→exit) lifts story coherence",
                "priority": 0.75,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V15_emotion_model_refresh" not in fails:
            fails.append("V15_emotion_model_refresh")
        state.failed_experiments = fails
        state.best_version = "V10_continuity_color"
        state.best_score = V10_BEST
        state.last_strategy = "REJECT V15 emotion_model_refresh; keep V10; next: reaction_cutaways"
        state.next_tasks = [
            {
                "title": "V16_reaction_cutaways",
                "hypothesis": "Insert guest/family reaction cutaways on vow/peak beats",
                "priority": 1.0,
            },
            {
                "title": "V16_kiss_temporal_nms",
                "hypothesis": "Temporal max-pool kiss/hug reduces single-frame false positives",
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
    jobs = [j for j in jobs if j.get("id") != "V15_emotion_model_refresh"]
    jobs.append(
        {
            "id": "V15_emotion_model_refresh",
            "script": "autolab/run_v15_emotion_refresh.py",
            "status": "done",
            "priority": 12,
            "hypothesis": (
                "MediaPipe blendshape smile/solemn cues refresh emotion beyond "
                "YuNet/proximity heuristics"
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
        "note": f"V15_emotion_model_refresh {verdict} {score:.2f} vs V10 {V10_BEST}",
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
