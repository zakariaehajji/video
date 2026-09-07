import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from mcp_server import (
    get_lab_status,
    update_lab_state,
    get_experiment_history,
    get_version_history,
)

from strategist import ask_strategist
from experiment_manager import create_experiment


ROOT = Path(__file__).resolve().parent.parent

load_dotenv(
    ROOT / "autolab" / ".env"
)


# ============================================================
# CONFIG
# ============================================================

DEFAULT_HOURS = 6

POLL_SECONDS = 10


# ============================================================
# TIME
# ============================================================

def now():
    return time.time()


def remaining_seconds(
    deadline: float,
) -> float:

    return max(
        0,
        deadline - now(),
    )


# ============================================================
# STRATEGIST
# ============================================================

def get_strategy():

    state = get_lab_status()

    experiments = get_experiment_history(
        limit=20
    )

    versions = get_version_history(
        limit=20
    )

    return ask_strategist(
        lab_state=state,
        recent_experiments=experiments,
        recent_versions=versions,
    )


# ============================================================
# LOGGING
# ============================================================

def log(message: str):

    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        f"[{timestamp}] {message}",
        flush=True,
    )


# ============================================================
# MAIN LOOP
# ============================================================

def run_lab(
    hours: float = DEFAULT_HOURS,
):

    duration = hours * 60 * 60

    started = now()

    deadline = started + duration

    update_lab_state(
        "remaining_time",
        str(int(duration)),
    )

    log(
        f"AutoLab started for {hours:.2f} hours."
    )

    log(
        "The orchestrator owns the research clock."
    )

    iteration = 0

    while now() < deadline:

        iteration += 1

        remaining = remaining_seconds(
            deadline
        )

        update_lab_state(
            "remaining_time",
            str(int(remaining)),
        )

        state = get_lab_status()

        log(
            f"Iteration {iteration}"
        )

        log(
            f"Current version: "
            f"{state.get('current_version')}"
        )

        log(
            f"Best version: "
            f"{state.get('best_version')}"
        )

        log(
            f"Best score: "
            f"{state.get('best_score')}"
        )

        log(
            f"Remaining: "
            f"{remaining / 3600:.2f}h"
        )

        # ----------------------------------------------------
        # STRATEGIC DECISION
        # ----------------------------------------------------

        log(
            "Asking strategist for highest-value experiment..."
        )

        strategy = get_strategy()

        log(
            json.dumps(
                strategy,
                indent=2,
            )
        )

        if strategy.get(
            "decision"
        ) == "STOP":

            log(
                "Strategist requested STOP."
            )

            break

        # ----------------------------------------------------
        # CREATE EXPERIMENT
        # ----------------------------------------------------

        current_version = state.get(
            "current_version",
            "V3",
        )

        target_version = strategy.get(
            "version_target",
            current_version,
        )

        experiment = create_experiment(
            strategy,
            target_version,
        )

        log(
            f"Created experiment: "
            f"{experiment['name']}"
        )

        # ----------------------------------------------------
        # IMPORTANT
        # ----------------------------------------------------
        #
        # At this stage we DON'T pretend that Cursor
        # executed the experiment.
        #
        # The next layer will connect this experiment
        # to actual Cursor/agent execution.
        #
        # ----------------------------------------------------

        log(
            "Experiment queued."
        )

        log(
            "Waiting for execution layer..."
        )

        # Prevent an accidental infinite API loop
        # while the execution layer is being built.

        time.sleep(
            min(
                POLL_SECONDS,
                remaining_seconds(deadline),
            )
        )

        if remaining_seconds(
            deadline
        ) <= 0:

            break

    update_lab_state(
        "remaining_time",
        "0",
    )

    log(
        "================================================"
    )

    log(
        "AUTOLAB SESSION FINISHED"
    )

    log(
        f"Iterations: {iteration}"
    )

    final_state = get_lab_status()

    log(
        json.dumps(
            final_state,
            indent=2,
        )
    )


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    hours = DEFAULT_HOURS

    if len(sys.argv) >= 2:

        if sys.argv[1] == "--hours":

            hours = float(
                sys.argv[2]
            )

    run_lab(hours)
