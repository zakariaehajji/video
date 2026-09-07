"""In-memory / JSON lab state the orchestrator and MCP expose."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autolab import db
from autolab.paths import EXPERIMENT_LOG, STATE_JSON, TASK_QUEUE, ensure_dirs


@dataclass
class LabState:
    current_version: str = "V3"
    best_version: str = "V3"
    best_score: float = 8.15
    current_experiment: str | None = None
    remaining_time_sec: float = 0.0
    elapsed_time_sec: float = 0.0
    session_duration_sec: float = 6 * 3600
    active_agents: list[str] = field(default_factory=list)
    failed_experiments: list[str] = field(default_factory=list)
    next_tasks: list[dict[str, Any]] = field(default_factory=list)
    experiments_run: int = 0
    candidates_run: int = 0
    last_strategy: str | None = None
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LabState":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def load_state() -> LabState:
    ensure_dirs()
    db.init_db()
    if STATE_JSON.exists():
        state = LabState.from_dict(json.loads(STATE_JSON.read_text(encoding="utf-8")))
    else:
        state = LabState()
    best = db.best_version()
    if best:
        state.best_version = best["version"]
        state.best_score = float(best["score"] or 0)
    counts = db.counts()
    state.experiments_run = counts["experiments"]
    state.candidates_run = counts["candidates"]
    state.failed_experiments = [
        f"{f.get('stage')}: {f.get('message')}" for f in db.recent_failures(10)
    ]
    if TASK_QUEUE.exists():
        try:
            state.next_tasks = json.loads(TASK_QUEUE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state.next_tasks = []
    state.updated_at = datetime.now(timezone.utc).isoformat()
    return state


def save_state(state: LabState) -> None:
    ensure_dirs()
    state.updated_at = datetime.now(timezone.utc).isoformat()
    STATE_JSON.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    TASK_QUEUE.write_text(json.dumps(state.next_tasks, indent=2), encoding="utf-8")


def append_experiment_log(text: str) -> None:
    ensure_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with EXPERIMENT_LOG.open("a", encoding="utf-8") as f:
        f.write(f"\n## {stamp}\n{text.rstrip()}\n")


def update_lab_state(**kwargs: Any) -> LabState:
    state = load_state()
    for k, v in kwargs.items():
        if hasattr(state, k):
            setattr(state, k, v)
    save_state(state)
    return state


def format_dashboard(state: LabState) -> str:
    rem = max(0, int(state.remaining_time_sec))
    el = max(0, int(state.elapsed_time_sec))
    def fmt(s: int) -> str:
        h, r = divmod(s, 3600)
        m, sec = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{sec:02d}"

    agents = ", ".join(state.active_agents) if state.active_agents else "none"
    if len(agents) > 22:
        agents = agents[:19] + "..."
    cur = (state.current_version or "-")[:22]
    best = (state.best_version or "-")[:22]
    return (
        "╔══════════════════════════════════════╗\n"
        "║       WEDDING AI AUTOLAB             ║\n"
        "╠══════════════════════════════════════╣\n"
        f"║ Elapsed:       {fmt(el):<22}║\n"
        f"║ Remaining:     {fmt(rem):<22}║\n"
        f"║ Current:       {cur:<22}║\n"
        f"║ Best:          {best:<22}║\n"
        f"║ Score:         {state.best_score:<22}║\n"
        f"║ Experiments:   {state.experiments_run:<22}║\n"
        f"║ Candidates:    {state.candidates_run:<22}║\n"
        f"║ Active agents: {agents:<22}║\n"
        "╚══════════════════════════════════════╝"
    )
