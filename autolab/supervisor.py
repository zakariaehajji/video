"""
Persistent AutoLab supervisor: owns the research clock and relaunches Cursor Agent.

This is NOT a fake timer. Each agent session may exit; the supervisor relaunches
until the deadline, while protecting V3 and recording logs.

Usage:
  .\\.venv\\Scripts\\python.exe autolab\\supervisor.py --hours 6
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "autolab" / "prompts"
RESULTS = ROOT / "autolab" / "results"
LOG_DIR = RESULTS / "session_logs"

START_PROMPT = PROMPTS / "START_6H_LAB.md"
MASTER_PROMPT = PROMPTS / "MASTER_AUTONOMOUS_LAB.md"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "supervisor.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_agent() -> str:
    from shutil import which

    path = which("agent")
    if path:
        return path
    candidate = Path.home() / "AppData" / "Local" / "cursor-agent" / "agent.cmd"
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError("Cursor Agent CLI 'agent' not found on PATH")


def agent_logged_in(agent: str) -> bool:
    try:
        proc = subprocess.run(
            [agent, "status"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        return "Not logged in" not in text and proc.returncode == 0
    except Exception as e:  # noqa: BLE001
        log(f"status check failed: {e}")
        return False


def build_continue_prompt(iteration: int, remaining_sec: float) -> str:
    master = MASTER_PROMPT.read_text(encoding="utf-8") if MASTER_PROMPT.exists() else ""
    start = START_PROMPT.read_text(encoding="utf-8") if START_PROMPT.exists() else ""
    hours_left = remaining_sec / 3600.0
    return (
        f"{start}\n\n"
        f"---\n"
        f"# SUPERVISOR RELAUNCH #{iteration}\n"
        f"Remaining research window: {hours_left:.2f} hours.\n"
        f"You may have been restarted because a previous agent session ended.\n"
        f"DO NOT restart from scratch if progress already exists.\n"
        f"Inspect Output/autolab/, autolab/state/, wedding_v3/, and experiment logs.\n"
        f"Resume at the highest-value unfinished experiment.\n"
        f"Continue V4→V5→V6… only with real renders + evaluations.\n"
        f"Never overwrite Output/wedding_v3/BEST_v3.mp4 without archiving.\n"
        f"Use wedding-autolab MCP tools when available.\n\n"
        f"---\n"
        f"# MASTER RULES\n"
        f"{master}\n"
    )


def run_one_agent_session(agent: str, prompt: str, iteration: int) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LOG_DIR / f"agent_iter_{iteration:03d}.log"
    log(f"Launching agent session #{iteration} → {out_path}")
    cmd = [
        agent,
        "-p",
        prompt,
        "--force",
        "--output-format",
        "text",
    ]
    with out_path.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=out,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            return proc.wait(timeout=None)
        except KeyboardInterrupt:
            proc.terminate()
            raise


def run_supervisor(hours: float = 6.0, max_iterations: int | None = None) -> None:
    agent = find_agent()
    if not agent_logged_in(agent):
        raise SystemExit(
            "Cursor Agent is not logged in. Run: agent login\n"
            "Then re-run the supervisor."
        )

    deadline = time.time() + hours * 3600
    log(f"Supervisor started. Deadline in {hours:.2f}h. Agent={agent}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "session_meta.json").write_text(
        json.dumps(
            {
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "hours": hours,
                "deadline_epoch": deadline,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    iteration = 0
    while time.time() < deadline:
        iteration += 1
        if max_iterations is not None and iteration > max_iterations:
            log(f"Hit max_iterations={max_iterations}")
            break
        remaining = max(0.0, deadline - time.time())
        prompt = build_continue_prompt(iteration, remaining)
        code = run_one_agent_session(agent, prompt, iteration)
        log(f"Agent session #{iteration} exited with code {code}")
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        # Brief pause before relaunch so we don't spin on instant failures
        pause = 15 if code == 0 else 60
        pause = min(pause, remaining)
        log(f"Relaunching in {pause:.0f}s ({remaining / 3600:.2f}h left)...")
        time.sleep(pause)

    log("SUPERVISOR SESSION FINISHED")
    meta = {
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "iterations": iteration,
        "hours_requested": hours,
    }
    (RESULTS / "session_meta_final.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, indent=2), flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=6.0)
    p.add_argument("--max-iterations", type=int, default=None)
    args = p.parse_args()
    run_supervisor(hours=args.hours, max_iterations=args.max_iterations)


if __name__ == "__main__":
    main()
