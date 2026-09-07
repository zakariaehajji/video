"""Canonical paths for the autonomous lab."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOLAB = Path(__file__).resolve().parent

AGENTS_DIR = AUTOLAB / "agents"
EXPERIMENTS_DIR = AUTOLAB / "experiments"
RESULTS_DIR = AUTOLAB / "results"
STATE_DIR = AUTOLAB / "state"
PROMPTS_DIR = AUTOLAB / "prompts"
DATASETS_DIR = AUTOLAB / "datasets"

DB_PATH = STATE_DIR / "lab.db"
STATE_JSON = STATE_DIR / "lab_state.json"
TASK_QUEUE = STATE_DIR / "task_queue.json"
EXPERIMENT_LOG = STATE_DIR / "experiment_log.md"

BEST_VIDEO = ROOT / "Output" / "wedding_v3" / "BEST_v3.mp4"
V3_OUT = ROOT / "Output" / "wedding_v3"
V3_CACHE = ROOT / "Output" / "v3_cache"


def ensure_dirs() -> None:
    for d in (
        AGENTS_DIR,
        EXPERIMENTS_DIR,
        RESULTS_DIR,
        STATE_DIR,
        PROMPTS_DIR,
        DATASETS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
