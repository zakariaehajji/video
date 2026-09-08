"""One-shot runner for V12_music_section_roles experiment.

Hypothesis: Tighter music-section→story-role mapping (energy-aware arc +
section-role ranking bias) lifts music_sync without regressing V10 continuity.

Compares against V10 best (8.69). Never overwrites BEST_v10 / BEST_v3.
Keeps V5 pace-hold, V7 titles, V8 tears cues, V10 color continuity.
Does NOT enable V9 VISUAL_BOOST or V11 PEAK_HOLD (both REJECTED / no gain).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V12_DIR = ROOT / "Output" / "autolab" / "V12"
V10_BEST = 8.69
V8_BEST = 8.60
V3 = 8.15
TAG = "autolab_music_section_roles"


def _role_stats(run_dir: Path) -> dict:
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
    by_sec: dict[str, Counter] = {}
    for p in picks:
        sec = str(p.get("section") or "?")
        role = str(p.get("role") or "?")
        by_sec.setdefault(sec, Counter())[role] += 1
    peaks = [p for p in picks if p.get("peak") or p.get("section") == "peak"]
    peak_intimate = sum(
        1
        for p in peaks
        if p.get("role") in ("couple", "portrait")
    )
    fit_reasons = sum(
        1
        for p in picks
        if any(
            r in (p.get("reasons") or [])
            for r in ("section-role-fit", "peak-emotion-role", "intro-establish", "outro-resolve")
        )
    )
    return {
        "n_picks": len(picks),
        "roles": dict(Counter(str(p.get("role")) for p in picks)),
        "sections": dict(Counter(str(p.get("section")) for p in picks)),
        "by_section": {k: dict(v) for k, v in by_sec.items()},
        "n_peaks": len(peaks),
        "peak_intimate_roles": peak_intimate,
        "peak_intimate_ratio": round(peak_intimate / max(1, len(peaks)), 4),
        "section_role_reason_hits": fit_reasons,
        "mean_score": round(
            sum(float(p.get("score") or 0) for p in picks) / len(picks), 4
        ),
        "mean_emotion": round(
            sum(float(p.get("emotion") or 0) for p in picks) / len(picks), 4
        ),
        "peak_mean_emotion": round(
            sum(float(p.get("emotion") or 0) for p in peaks) / max(1, len(peaks)), 4
        ),
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
            "Restore from wedding_* caches before running V12."
        )


def main() -> int:
    V12_DIR.mkdir(parents=True, exist_ok=True)
    _assert_wedding_pool()

    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
    os.environ["WEDDING_V3_COLOR_CONTINUITY"] = "1"
    os.environ["WEDDING_V3_COLOR_MATCH"] = "1"
    os.environ["WEDDING_V3_MUSIC_SECTION_ROLES"] = "1"
    os.environ.pop("WEDDING_V3_VISUAL_BOOST", None)
    os.environ.pop("WEDDING_V3_PEAK_HOLD", None)

    import wedding_v3.story as story_mod
    import wedding_v3.titles as titles_mod
    import wedding_v3.critic as critic_mod
    import wedding_v3.cinematic as cine_mod
    import wedding_v3.ranking as ranking_mod

    story_mod.PACE_HOLD_FLOOR = True
    story_mod.PEAK_HOLD = False
    story_mod.MUSIC_SECTION_ROLES = True
    titles_mod.TITLE_CARDS = True
    critic_mod.TITLE_CARDS = True
    critic_mod.COLOR_CONTINUITY = True
    critic_mod.PEAK_HOLD = False
    critic_mod.MUSIC_SECTION_ROLES = True
    cine_mod.TITLE_CARDS = True
    cine_mod.COLOR_MATCH = True
    ranking_mod.COLOR_CONTINUITY = True
    ranking_mod.PEAK_HOLD = False
    ranking_mod.MUSIC_SECTION_ROLES = True
    ranking_mod.VISUAL_BOOST = False

    print("=== V12_music_section_roles render ===", flush=True)
    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V12",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V12_music_section_roles",
            "status": "failed",
            "error": err,
            "v10_baseline": V10_BEST,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V12_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V12_music_section_roles FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V12_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    role_stats = _role_stats(run_dir)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v12.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V12_music_section_roles",
                hypothesis=(
                    "Tighter music-section→story-role mapping lifts music_sync"
                ),
                configuration={
                    "tag": TAG,
                    "music_section_roles": True,
                    "pace_hold": True,
                    "color_continuity": True,
                    "peak_hold": False,
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
                "V12_music_section_roles",
                score,
                promoted,
                notes=f"music_section_roles KEEP delta={eval_result.get('delta')}",
                parent="V10_continuity_color",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    eval_data = {
        "experiment": "V12_music_section_roles",
        "status": "completed",
        "hypothesis": (
            "Tighter music-section→story-role mapping lifts music_sync"
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
        "role_stats": role_stats,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V12_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V12_music_section_roles completed.",
                f"run_dir={run_dir}",
                f"roles={role_stats}",
                f"best_score={score} (V10 baseline {V10_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V12_music_section_roles"
    state.current_version = "V12_music_section_roles"
    state.experiments_run = int(getattr(state, "experiments_run", 0) or 0) + 1
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V12_music_section_roles"
        state.best_score = score
        fails = [f for f in (state.failed_experiments or []) if f != "V12_music_section_roles"]
        state.failed_experiments = fails
        state.last_strategy = "KEEP V12 music_section_roles; next: soft visual quality"
        state.next_tasks = [
            {
                "title": "V13_visual_quality_soft",
                "hypothesis": "Soft CQ preference without V9 consecutive-source failure",
                "priority": 1.0,
            },
            {
                "title": "V13_peak_hold_soft",
                "hypothesis": "Milder peak linger (+0.25s top-3 only) without duration-weight critic",
                "priority": 0.7,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V12_music_section_roles" not in fails:
            fails.append("V12_music_section_roles")
        state.failed_experiments = fails
        state.best_version = "V10_continuity_color"
        state.best_score = V10_BEST
        state.last_strategy = "REJECT V12 music_section_roles; keep V10; next: soft visual or peak_hold_soft"
        state.next_tasks = [
            {
                "title": "V13_visual_quality_soft",
                "hypothesis": "Soft CQ preference without V9 consecutive-source failure",
                "priority": 1.0,
            },
            {
                "title": "V12_peak_hold_soft",
                "hypothesis": "Milder peak linger (+0.25s top-3 only) without duration-weight critic",
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
    jobs = [j for j in jobs if j.get("id") != "V12_music_section_roles"]
    jobs.append(
        {
            "id": "V12_music_section_roles",
            "script": "autolab/run_v12_music_roles.py",
            "status": "done",
            "priority": 9,
            "hypothesis": "Tighter music-section→story-role mapping lifts music_sync",
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
        "note": f"V12_music_section_roles {verdict} {score:.2f} vs V10 {V10_BEST}",
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
