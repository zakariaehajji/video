import json
from pathlib import Path

from mcp_server import (
    add_task,
    start_task,
    complete_task,
    record_experiment,
)


ROOT = Path(__file__).resolve().parent.parent


def create_experiment(
    strategy: dict,
    version: str,
) -> dict:

    experiment = strategy.get(
        "experiment",
        {},
    )

    name = experiment.get(
        "name",
        "unnamed_experiment",
    )

    hypothesis = strategy.get(
        "hypothesis",
        "",
    )

    priority = int(
        strategy.get(
            "priority",
            5,
        )
    )

    task_id = (
        f"{version}_{name}"
    )

    add_task(
        task_id=task_id,
        title=name,
        description=json.dumps(
            strategy,
            indent=2,
        ),
        priority=priority,
    )

    return {
        "task_id": task_id,
        "name": name,
        "hypothesis": hypothesis,
        "priority": priority,
    }


def mark_experiment_running(
    task_id: str,
):

    start_task(task_id)


def mark_experiment_complete(
    task_id: str,
    result: str,
):

    complete_task(
        task_id,
        result,
    )


def save_experiment(
    experiment_id: str,
    version: str,
    strategy: dict,
    score: float,
    status: str,
    result: str,
    runtime_seconds: float,
):

    record_experiment(
        experiment_id=experiment_id,
        version=version,
        hypothesis=strategy.get(
            "hypothesis",
            "",
        ),
        configuration=json.dumps(
            strategy,
        ),
        score=score,
        status=status,
        result=result,
        runtime_seconds=runtime_seconds,
    )
