"""Execute experiments: local wedding_v3 pipeline and/or Cursor Agent CLI tasks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from autolab.paths import AGENTS_DIR, ROOT, V3_CACHE, ensure_dirs
from autolab.strategist import Strategy


def find_cursor_agent() -> str | None:
    for name in ("cursor-agent", "agent"):
        path = shutil.which(name)
        if path:
            return path
    # Common Cursor install locations (Windows)
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "cursor-agent" / "cursor-agent.exe",
        Path.home() / ".local" / "bin" / "cursor-agent",
        Path.home() / ".cursor" / "bin" / "cursor-agent.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def queue_cursor_task(strategy: Strategy) -> Path:
    """Write a durable task file Cursor Agent (or a human) can execute."""
    ensure_dirs()
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = AGENTS_DIR / f"task_{strategy.next_experiment}.md"
    body = (
        f"# Autolab task: {strategy.next_experiment}\n\n"
        f"**Hypothesis:** {strategy.hypothesis}\n\n"
        f"**Category:** {strategy.category}\n\n"
        f"**Expected gain:** {strategy.expected_gain}\n\n"
        f"**Rationale:** {strategy.rationale}\n\n"
        f"## Cursor Agent instructions\n\n{strategy.cursor_task}\n\n"
        f"## Pipeline config\n\n```json\n{json.dumps(strategy.pipeline_config, indent=2)}\n```\n\n"
        "When done: update autolab state via MCP `update_lab_state` / `record_experiment_result`.\n"
        "Never overwrite the previous BEST without archiving.\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def run_with_cursor(strategy: Strategy, timeout_sec: int = 1800) -> dict[str, Any]:
    task_path = queue_cursor_task(strategy)
    agent = find_cursor_agent()
    if not agent:
        return {
            "ok": False,
            "mode": "queued_only",
            "task_path": str(task_path),
            "message": (
                "cursor-agent CLI not installed. Task queued at "
                f"{task_path}. Install Cursor Agent CLI, or execute the task in Cursor chat "
                "using wedding-autolab MCP tools."
            ),
        }
    prompt = task_path.read_text(encoding="utf-8")
    cmd = [agent, "-p", "--force", prompt]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "mode": "cursor-agent",
            "task_path": str(task_path),
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-8000:],
            "stderr": (proc.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "mode": "cursor-agent",
            "task_path": str(task_path),
            "message": f"cursor-agent timed out after {timeout_sec}s",
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "mode": "queued_only",
            "task_path": str(task_path),
            "message": "cursor-agent not found at runtime",
        }


def run_pipeline(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run wedding_v3 multi-candidate pipeline locally (no Cursor required)."""
    from wedding_v3.pipeline import run_candidates

    config = dict(config or {})
    audio_stem = config.get("audio_stem", "music_428")
    audio = ROOT / "resource" / "audio" / "wedding_web" / f"{audio_stem}.mp3"
    if not audio.exists():
        # any available wedding track
        aud_dir = ROOT / "resource" / "audio" / "wedding_web"
        mp3s = sorted(aud_dir.glob("*.mp3")) if aud_dir.exists() else []
        if not mp3s:
            return {"ok": False, "error": f"missing audio {audio}"}
        audio = mp3s[0]

    tag = config.get("tag", f"autolab_{int(time.time())}")
    out_root = config.get("out_root")
    if out_root:
        out_root = Path(out_root)
        if not out_root.is_absolute():
            out_root = ROOT / out_root
    t0 = time.time()
    try:
        result = run_candidates(
            audio=audio,
            styles=config.get("styles"),
            profiles=config.get("profiles"),
            render_top=int(config.get("render_top", 2)),
            tag=tag,
            out_root=out_root,
        )
        runtime = time.time() - t0
        run_dir = (out_root if out_root else ROOT / "Output" / "wedding_v3") / tag
        return {
            "ok": True,
            "runtime": runtime,
            "tag": tag,
            "run_dir": str(run_dir),
            "result": result if isinstance(result, dict) else {"raw": str(result)},
            "audio": str(audio),
            "pool": str(V3_CACHE / "shots" / "pool.json"),
        }
    except Exception as e:  # noqa: BLE001 — surface to orchestrator/DB
        return {"ok": False, "error": str(e), "runtime": time.time() - t0, "tag": tag}
