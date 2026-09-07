import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

LOG_DIR = (
    ROOT
    / "autolab"
    / "results"
    / "session_logs"
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

SESSION_DIR = (
    LOG_DIR
    / datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
)

SESSION_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


SESSION_HOURS = 6

AGENT_MAX_SECONDS = 45 * 60

IDLE_TIMEOUT_SECONDS = 8 * 60

RESTART_DELAY = 5


WATCH_ROOTS = [
    ROOT / "wedding_v3",
    ROOT / "Output",
    ROOT / "autolab",
]


def log(message):

    text = (
        f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
        f"{message}"
    )

    print(
        text,
        flush=True,
    )

    with (
        SESSION_DIR
        / "supervisor.log"
    ).open(
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            text + "\n"
        )


def snapshot():

    result = {}

    for root in WATCH_ROOTS:

        if not root.exists():
            continue

        try:

            for path in root.rglob("*"):

                if not path.is_file():
                    continue

                # Skip noisy/volatile paths
                p = str(path).replace("\\", "/").lower()
                if "/session_logs/" in p:
                    continue
                if p.endswith(".pyc") or "/__pycache__/" in p:
                    continue

                try:

                    stat = path.stat()

                    result[str(path)] = (
                        stat.st_mtime_ns,
                        stat.st_size,
                    )

                except OSError:
                    pass

        except Exception:
            pass

    return result


def changed(
    before,
    after,
):

    return before != after


def git_status():

    try:

        result = subprocess.run(
            [
                "git",
                "status",
                "--short",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        return result.stdout.strip()

    except Exception:

        return ""


def checkpoint(message):

    try:

        status = git_status()

        if not status:
            return

        subprocess.run(
            [
                "git",
                "add",
                "-A",
            ],
            cwd=ROOT,
            timeout=60,
        )

        result = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                message,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:

            log(
                f"Checkpoint: {message}"
            )

        else:

            log(
                "Checkpoint failed: "
                + result.stderr[-500:]
            )

    except Exception as exc:

        log(
            f"Checkpoint exception: {exc}"
        )


def prompt_for_cycle(
    cycle,
    remaining,
):

    return f"""
You are the execution agent for the autonomous Wedding AI Lab.

CYCLE: {cycle}

REMAINING SESSION TIME:
{remaining / 3600:.2f} hours

You MUST perform actual work in this cycle.

Read:

autolab/prompts/MASTER_AUTONOMOUS_LAB.md
autolab/prompts/START_6H_LAB.md
.cursor/rules/autonomous-lab.mdc

Inspect the current repository and AutoLab state.

Use wedding-autolab MCP when useful.

DO NOT merely describe a solution.

DO NOT wait for the user.

DO NOT only create a plan.

Choose ONE highest-value experiment that can genuinely be executed now.

Then:

1. implement it
2. run relevant commands/tests
3. render a real candidate when appropriate
4. evaluate the result
5. compare against the current best
6. keep or reject based on evidence
7. record the experiment
8. leave the repository coherent

If the previous cycle failed, diagnose and recover.

Never invent results.

Never claim a render happened unless a real output file exists.

Never overwrite V3 or the current best.

When the experiment is genuinely finished, EXIT.

Your final response must contain:

EXPERIMENT:
FILES_CHANGED:
COMMANDS_RUN:
RENDER:
EVALUATION:
SCORE:
DECISION:
REMAINING_WEAKNESS:
NEXT_EXPERIMENT:

Do not sit waiting for another prompt.
"""


def run_cycle(
    cycle,
    deadline,
):

    remaining = (
        deadline
        - time.time()
    )

    prompt = prompt_for_cycle(
        cycle,
        remaining,
    )

    output_path = (
        SESSION_DIR
        / f"agent_{cycle:03d}.log"
    )

    log(
        f"Launching Agent cycle {cycle}"
    )

    log(
        f"Output: {output_path}"
    )

    before = snapshot()

    start = time.time()

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as output:

        process = subprocess.Popen(
            [
                "agent",
                "--trust",
                "--force",
                "-p",
                prompt,
                "--output-format",
                "text",
            ],
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
        )

    log(
        f"Agent PID: {process.pid}"
    )

    last_log_size = 0

    last_real_activity = start

    last_heartbeat_minute = -1

    while True:

        now = time.time()

        # ---------------------------------------------
        # Session deadline
        # ---------------------------------------------

        if now >= deadline:

            log(
                "Session deadline reached."
            )

            try:
                process.kill()
            except Exception:
                pass

            return "SESSION_DEADLINE"

        # ---------------------------------------------
        # Agent maximum cycle time
        # ---------------------------------------------

        if now - start >= AGENT_MAX_SECONDS:

            log(
                "Agent exceeded maximum cycle time."
            )

            try:
                process.kill()
            except Exception:
                pass

            return "AGENT_TIMEOUT"

        # ---------------------------------------------
        # Check process
        # ---------------------------------------------

        code = process.poll()

        # ---------------------------------------------
        # Check output activity
        # ---------------------------------------------

        try:

            log_size = (
                output_path.stat().st_size
            )

        except OSError:

            log_size = 0

        if log_size != last_log_size:

            last_log_size = log_size

            last_real_activity = now

            log(
                f"Agent output activity: "
                f"{log_size} bytes"
            )

        # ---------------------------------------------
        # Check filesystem activity
        # ---------------------------------------------

        after = snapshot()

        if changed(
            before,
            after,
        ):

            before = after

            last_real_activity = now

            log(
                "REAL FILE ACTIVITY detected."
            )

        # ---------------------------------------------
        # Agent finished
        # ---------------------------------------------

        if code is not None:

            duration = (
                now - start
            )

            log(
                f"Agent exited: "
                f"code={code}, "
                f"duration={duration:.1f}s"
            )

            return (
                "SUCCESS"
                if code == 0
                else "FAILED"
            )

        # ---------------------------------------------
        # Idle watchdog
        # ---------------------------------------------

        idle = (
            now
            - last_real_activity
        )

        if idle >= IDLE_TIMEOUT_SECONDS:

            log(
                f"Agent appears stuck. "
                f"No output/file activity for "
                f"{idle / 60:.1f} minutes."
            )

            try:
                process.kill()
            except Exception:
                pass

            return "IDLE_KILLED"

        # ---------------------------------------------
        # Heartbeat
        # ---------------------------------------------

        minute = int((now - start) // 60)

        if minute != last_heartbeat_minute:

            last_heartbeat_minute = minute

            log(
                f"Heartbeat: "
                f"cycle={cycle}, "
                f"runtime={(now-start)/60:.1f}m, "
                f"idle={idle/60:.1f}m"
            )

        time.sleep(2)


def main():

    hours = SESSION_HOURS

    if (
        len(sys.argv) >= 3
        and sys.argv[1] == "--hours"
    ):

        hours = float(
            sys.argv[2]
        )

    started = time.time()

    deadline = (
        started
        + hours * 3600
    )

    log(
        "========================================"
    )

    log(
        "AUTOLAB SUPERVISOR"
    )

    log(
        f"Duration: {hours} hours"
    )

    log(
        f"Deadline: "
        f"{datetime.fromtimestamp(deadline)}"
    )

    log(
        f"Session dir: {SESSION_DIR}"
    )

    log(
        "========================================"
    )

    checkpoint(
        "AutoLab before autonomous session"
    )

    cycle = 0

    while time.time() < deadline:

        cycle += 1

        remaining = (
            deadline
            - time.time()
        )

        log(
            "----------------------------------------"
        )

        log(
            f"CYCLE {cycle}"
        )

        log(
            f"Remaining: "
            f"{remaining / 3600:.2f}h"
        )

        result = run_cycle(
            cycle,
            deadline,
        )

        log(
            f"CYCLE {cycle} RESULT: {result}"
        )

        # Save machine-readable cycle result.
        report = {
            "cycle": cycle,
            "result": result,
            "timestamp": datetime.now().isoformat(),
            "remaining_seconds":
                max(
                    0,
                    deadline - time.time(),
                ),
            "git_status":
                git_status(),
        }

        (
            SESSION_DIR
            / f"cycle_{cycle:03d}.json"
        ).write_text(
            json.dumps(
                report,
                indent=2,
            ),
            encoding="utf-8",
        )

        checkpoint(
            f"AutoLab cycle {cycle}"
        )

        if time.time() >= deadline:

            break

        log(
            f"Restarting in {RESTART_DELAY}s"
        )

        time.sleep(
            RESTART_DELAY
        )

    checkpoint(
        "AutoLab final autonomous session"
    )

    log(
        "========================================"
    )

    log(
        "6-HOUR SESSION FINISHED"
    )

    log(
        f"Cycles completed: {cycle}"
    )

    log(
        "========================================"
    )


if __name__ == "__main__":
    main()
