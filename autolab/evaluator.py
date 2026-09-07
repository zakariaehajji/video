"""Evaluation bridge to wedding_v3 critic + promotion rules."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from autolab.paths import BEST_VIDEO, RESULTS_DIR, ROOT, ensure_dirs


def evaluate_run(run_dir: Path, best_score: float) -> dict[str, Any]:
    """Read leaderboard/critique JSON from a wedding_v3 run directory."""
    run_dir = Path(run_dir)
    leaderboard = run_dir / "leaderboard.json"
    critique: dict[str, Any] = {}
    video = None
    score = 0.0

    if leaderboard.exists():
        data = json.loads(leaderboard.read_text(encoding="utf-8"))
        # pipeline.py writes {leaderboard: [...], rendered: [...], best: {...}}
        if isinstance(data, dict) and "leaderboard" in data:
            board = data.get("leaderboard") or []
            top = board[0] if board else {}
            score = float(top.get("overall") or 0)
            rendered = data.get("rendered") or []
            best = data.get("best") or (rendered[0] if rendered else None)
            if isinstance(best, dict):
                video = best.get("path")
                score = float(best.get("overall") or score)
            # attach plan critique if present
            name = top.get("name")
            if name:
                cpath = run_dir / "plans" / f"{name}_critique.json"
                if cpath.exists():
                    critique = json.loads(cpath.read_text(encoding="utf-8"))
                else:
                    critique = {"overall": score, "name": name, "style": top.get("style"), "profile": top.get("profile")}
            else:
                critique = {"overall": score}
        elif isinstance(data, list) and data:
            top = data[0]
            score = float(top.get("score") or top.get("overall") or 0)
            critique = top.get("critique") or top
            video = top.get("video") or top.get("path")
        elif isinstance(data, dict):
            top = data.get("best") or data.get("winner") or data
            if isinstance(top, list) and top:
                top = top[0]
            score = float(
                top.get("score") or top.get("overall") or top.get("critique", {}).get("overall") or 0
            )
            critique = top.get("critique") or top
            video = top.get("video") or top.get("path")
    else:
        plans = sorted((run_dir / "plans").glob("*_critique.json")) if (run_dir / "plans").exists() else []
        if not plans:
            return {
                "ok": False,
                "score": 0.0,
                "better_than_best": False,
                "problems": ["no leaderboard or critiques found"],
                "path": str(run_dir),
            }
        best_s = -1.0
        best_data: dict[str, Any] = {}
        for p in plans:
            data = json.loads(p.read_text(encoding="utf-8"))
            overall = float(data.get("overall") or data.get("critique", {}).get("overall") or 0)
            if overall > best_s:
                best_s = overall
                best_data = data
        score = best_s
        critique = best_data

    better = score > best_score + 1e-6
    return {
        "ok": True,
        "score": score,
        "better_than_best": better,
        "delta": round(score - best_score, 3),
        "critique": critique,
        "video": video,
        "path": str(run_dir),
        "problems": (critique.get("problems") if isinstance(critique, dict) else None) or [],
        "recommendations": (critique.get("recommendations") if isinstance(critique, dict) else None)
        or [],
    }


def promote_best(video_path: Path | str | None, version: str, score: float) -> str | None:
    """Copy winning render to BEST path without deleting prior best archive."""
    ensure_dirs()
    if not video_path:
        return None
    src = Path(video_path)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        return None
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # Archive previous best
    if BEST_VIDEO.exists():
        archive = RESULTS_DIR / f"BEST_archive_before_{version}.mp4"
        shutil.copy2(BEST_VIDEO, archive)
    BEST_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, BEST_VIDEO)
    meta = RESULTS_DIR / f"{version}_promo.json"
    meta.write_text(
        json.dumps({"version": version, "score": score, "source": str(src)}, indent=2),
        encoding="utf-8",
    )
    return str(BEST_VIDEO)


def load_latest_critique_summary() -> dict[str, Any] | None:
    sprint = ROOT / "Output" / "wedding_v3" / "sprint_music_428_v3b" / "leaderboard.json"
    if sprint.exists():
        data = json.loads(sprint.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
    return None
