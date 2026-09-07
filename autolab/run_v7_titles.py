"""One-shot runner for V7_title_cards experiment.

Hypothesis: Soft black intro/outro title cards raise polish and wedding
feeling without harming V6 emotion/music_sync (pace-hold + kiss/hug pool kept).

Compares against V6 best (8.42). Never overwrites BEST_v6 / BEST_v3.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from autolab.evaluator import evaluate_run
from autolab.paths import ROOT
from autolab.runner import run_pipeline
from autolab.state import append_experiment_log, load_state, save_state

V7_DIR = ROOT / "Output" / "autolab" / "V7"
V6_BEST = 8.42
V5_BEST = 8.22
V3 = 8.15
TAG = "autolab_title_cards"


def main() -> int:
    V7_DIR.mkdir(parents=True, exist_ok=True)

    # Keep V5/V6 improvements active; enable V7 title cards only in this process.
    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    os.environ["WEDDING_V3_TITLE_CARDS"] = "1"
    import wedding_v3.story as story_mod
    import wedding_v3.titles as titles_mod
    import wedding_v3.critic as critic_mod
    import wedding_v3.cinematic as cine_mod

    story_mod.PACE_HOLD_FLOOR = True
    titles_mod.TITLE_CARDS = True
    critic_mod.TITLE_CARDS = True
    cine_mod.TITLE_CARDS = True

    print("=== V7_title_cards render ===", flush=True)
    print(
        f"content_duration={titles_mod.content_duration():.2f}s "
        f"(intro={titles_mod.INTRO_DUR}, outro={titles_mod.OUTRO_DUR})",
        flush=True,
    )

    run_result = run_pipeline(
        {
            "styles": ["emotional", "classic"],
            "profiles": ["A_emotion", "D_balanced"],
            "render_top": 2,
            "tag": TAG,
            "audio_stem": "music_428",
            "out_root": "Output/autolab/V7",
        }
    )
    if not run_result.get("ok"):
        err = run_result.get("error", "unknown")
        print(f"FAILED: {err}", flush=True)
        eval_data = {
            "experiment": "V7_title_cards",
            "status": "failed",
            "error": err,
            "v6_baseline": V6_BEST,
            "verdict": "REJECT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (V7_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")
        append_experiment_log(f"V7_title_cards FAILED: {err}")
        return 1

    run_dir = Path(run_result["run_dir"])
    for mp4 in run_dir.glob("*.mp4"):
        dest = V7_DIR / mp4.name
        if mp4.resolve() != dest.resolve():
            shutil.copy2(mp4, dest)

    eval_result = evaluate_run(run_dir, V6_BEST)
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
        dest = ROOT / "Output" / "autolab" / "BEST_v7.mp4"
        shutil.copy2(best_src, dest)
        promoted = str(dest)
        try:
            from autolab import db as lab_db

            lab_db.init_db()
            eid = lab_db.insert_experiment(
                version="V7_title_cards",
                hypothesis=(
                    "Soft intro/outro title cards raise polish and wedding feeling"
                ),
                configuration={"tag": TAG, "gate": "WEDDING_V3_TITLE_CARDS=1"},
                status="running",
            )
            lab_db.finish_experiment(
                eid,
                score=score,
                runtime=float(run_result.get("runtime") or 0.0),
                result=f"KEEP vs V6 {V6_BEST}; promoted {dest}",
                status="completed",
            )
            lab_db.promote_version(
                "V7_title_cards",
                score,
                promoted,
                notes=f"title cards KEEP delta={eval_result.get('delta')}",
                parent="V6_emotion_kiss_hug",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"db promote warning: {exc}", flush=True)

    # Evidence: title card clips must exist in a build folder for top render.
    title_evidence = []
    builds = run_dir / "builds"
    if builds.exists():
        for p in builds.rglob("title_*.mp4"):
            title_evidence.append(str(p))

    eval_data = {
        "experiment": "V7_title_cards",
        "status": "completed",
        "hypothesis": (
            "Soft intro/outro title cards raise polish and wedding feeling "
            "while keeping V6 intimacy + pace-hold"
        ),
        "v6_baseline": V6_BEST,
        "v5_baseline": V5_BEST,
        "v3_baseline": V3,
        "best_score": score,
        "delta_vs_v6": eval_result.get("delta"),
        "delta_vs_v3": round(score - V3, 3),
        "verdict": verdict,
        "run_dir": str(run_dir),
        "runtime_sec": run_result.get("runtime"),
        "title_card_files": title_evidence,
        "leaderboard": leaderboard.get("leaderboard", []),
        "rendered": leaderboard.get("rendered", []),
        "best": best,
        "promoted": promoted,
        "critique": eval_result.get("critique"),
        "problems": eval_result.get("problems"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (V7_DIR / "EVAL.json").write_text(json.dumps(eval_data, indent=2), encoding="utf-8")

    append_experiment_log(
        "\n".join(
            [
                "V7_title_cards completed.",
                f"run_dir={run_dir}",
                f"best_score={score} (V6 baseline {V6_BEST})",
                f"verdict={verdict}",
                f"problems={eval_result.get('problems')}",
                f"promoted={promoted}",
                f"title_cards={len(title_evidence)}",
            ]
        )
    )

    state = load_state()
    state.current_experiment = "V7_title_cards"
    state.current_version = "V7_title_cards"
    state.candidates_run += len(leaderboard.get("rendered", []))
    if verdict == "KEEP":
        state.best_version = "V7_title_cards"
        state.best_score = score
        state.last_strategy = "KEEP V7 titles; next: tears/reaction"
        state.next_tasks = [
            {
                "title": "V8_tears_reaction",
                "hypothesis": "Stronger tear/reaction cues lift emotion beyond proximity kiss/hug",
                "priority": 1.0,
            },
            {
                "title": "V8_visual_quality",
                "hypothesis": "Prefer higher cinematic_quality shots to lift visual_quality ~6.2",
                "priority": 0.85,
            },
        ]
    else:
        fails = list(state.failed_experiments or [])
        if "V7_title_cards" not in fails:
            fails.append("V7_title_cards")
        state.failed_experiments = fails
        state.last_strategy = "REJECT V7 titles; keep V6; next: tears/reaction"
        state.next_tasks = [
            {
                "title": "V7_tears_reaction",
                "hypothesis": "Stronger tear/reaction cues lift emotion beyond proximity kiss/hug",
                "priority": 1.0,
            },
            {
                "title": "V7_visual_quality",
                "hypothesis": "Prefer higher cinematic_quality shots to lift visual_quality ~6.2",
                "priority": 0.8,
            },
        ]
    save_state(state)
    (ROOT / "autolab" / "state" / "task_queue.json").write_text(
        json.dumps(state.next_tasks, indent=2), encoding="utf-8"
    )

    # Update pending jobs record
    pending_path = ROOT / "autolab" / "pending_jobs.json"
    try:
        jobs = json.loads(pending_path.read_text(encoding="utf-8"))
    except Exception:
        jobs = []
    jobs = [j for j in jobs if j.get("id") != "V7_title_cards"]
    jobs.append(
        {
            "id": "V7_title_cards",
            "script": "autolab/run_v7_titles.py",
            "status": "done",
            "priority": 4,
            "hypothesis": "Soft title/outro cards raise polish and wedding feeling",
            "depends_on": "V6_emotion_kiss_hug",
            "returncode": 0 if verdict else 1,
            "score": score,
            "verdict": verdict,
        }
    )
    pending_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    blocker = {
        "blocker": None,
        "cleared_at": datetime.now(timezone.utc).isoformat(),
        "note": f"V7_title_cards {verdict} {score:.2f} vs V6 {V6_BEST}",
        "best_version": state.best_version,
        "best_score": state.best_score,
        "renders_executed": True,
    }
    (ROOT / "autolab" / "results" / "BLOCKER.json").write_text(
        json.dumps(blocker, indent=2), encoding="utf-8"
    )

    print(json.dumps(eval_data, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
