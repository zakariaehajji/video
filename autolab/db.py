"""SQLite experiment database for the autonomous lab."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from autolab.paths import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    hypothesis TEXT,
    configuration TEXT,
    score REAL,
    runtime REAL,
    result TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT UNIQUE NOT NULL,
    parent_version TEXT,
    score REAL,
    path TEXT,
    notes TEXT,
    is_best INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER,
    name TEXT,
    style TEXT,
    profile TEXT,
    score REAL,
    path TEXT,
    critique TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(experiment_id) REFERENCES experiments(id)
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT,
    status TEXT DEFAULT 'idle',
    last_task TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    path TEXT,
    kind TEXT,
    meta TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    provider TEXT,
    purpose TEXT,
    meta TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id INTEGER,
    stage TEXT,
    message TEXT,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(experiment_id) REFERENCES experiments(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    priority REAL DEFAULT 0.5,
    status TEXT DEFAULT 'queued',
    assigned_agent TEXT,
    experiment_id INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(experiment_id) REFERENCES experiments(id)
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after early lab.db schemas."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(versions)").fetchall()}
    if "is_best" not in cols:
        conn.execute("ALTER TABLE versions ADD COLUMN is_best INTEGER DEFAULT 0")
    if "parent_version" not in cols:
        conn.execute("ALTER TABLE versions ADD COLUMN parent_version TEXT")
    # Ensure at least one best row when versions exist but none flagged.
    n = conn.execute("SELECT COUNT(*) AS c FROM versions").fetchone()["c"]
    best_n = conn.execute(
        "SELECT COUNT(*) AS c FROM versions WHERE is_best=1"
    ).fetchone()["c"]
    if n > 0 and best_n == 0:
        top = conn.execute(
            "SELECT id FROM versions ORDER BY score DESC, id ASC LIMIT 1"
        ).fetchone()
        if top:
            conn.execute("UPDATE versions SET is_best=1 WHERE id=?", (top["id"],))

    exp_cols = {row[1] for row in conn.execute("PRAGMA table_info(experiments)").fetchall()}
    if "runtime" not in exp_cols and "runtime_seconds" in exp_cols:
        # Older DBs used runtime_seconds; expose runtime alias column for code paths.
        conn.execute("ALTER TABLE experiments ADD COLUMN runtime REAL")
        conn.execute(
            "UPDATE experiments SET runtime=runtime_seconds WHERE runtime IS NULL"
        )
    elif "runtime" not in exp_cols:
        conn.execute("ALTER TABLE experiments ADD COLUMN runtime REAL")
    if "result" not in exp_cols:
        conn.execute("ALTER TABLE experiments ADD COLUMN result TEXT")


def init_db() -> None:
    ensure_dirs()
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        # Seed baseline V3 if empty
        n = conn.execute("SELECT COUNT(*) AS c FROM versions").fetchone()["c"]
        if n == 0:
            now = utcnow()
            conn.execute(
                """
                INSERT INTO versions(version, parent_version, score, path, notes, is_best, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    "V3",
                    "V2",
                    8.15,
                    "Output/wedding_v3/BEST_v3.mp4",
                    "emotional + A_emotion on music_428; auto-critic peak",
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO experiments(version, hypothesis, configuration, score, runtime, result, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'completed', ?)
                """,
                (
                    "V3",
                    "Multi-candidate shot/music/story ranking beats single-pass V2 montage",
                    json.dumps({"style": "emotional", "profile": "A_emotion", "audio": "music_428"}),
                    8.15,
                    None,
                    "promoted BEST_v3.mp4",
                    now,
                ),
            )
            for name, purpose in (
                ("openai-strategist", "strategy"),
                ("openai-fast", "classification"),
                ("wedding_v3_critic", "evaluation"),
            ):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO models(name, provider, purpose, meta, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, "local/openai", purpose, "{}", now),
                )


def insert_experiment(
    *,
    version: str,
    hypothesis: str,
    configuration: dict[str, Any] | None = None,
    status: str = "running",
) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO experiments(version, hypothesis, configuration, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (version, hypothesis, json.dumps(configuration or {}), status, utcnow()),
        )
        return int(cur.lastrowid)


def finish_experiment(
    experiment_id: int,
    *,
    score: float | None,
    runtime: float | None,
    result: str,
    status: str = "completed",
) -> None:
    with connect() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(experiments)").fetchall()}
        sets = ["score=?", "result=?", "status=?"]
        vals: list[Any] = [score, result, status]
        if "runtime" in cols:
            sets.insert(1, "runtime=?")
            vals.insert(1, runtime)
        if "runtime_seconds" in cols:
            sets.insert(1, "runtime_seconds=?")
            vals.insert(1, runtime)
        vals.append(experiment_id)
        conn.execute(
            f"UPDATE experiments SET {', '.join(sets)} WHERE id=?",
            vals,
        )


def record_failure(experiment_id: int | None, stage: str, message: str, details: dict | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO failures(experiment_id, stage, message, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (experiment_id, stage, message, json.dumps(details or {}), utcnow()),
        )


def enqueue_task(title: str, description: str, priority: float = 0.5) -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks(title, description, priority, status, created_at)
            VALUES (?, ?, ?, 'queued', ?)
            """,
            (title, description, priority, utcnow()),
        )
        return int(cur.lastrowid)


def next_task() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM tasks
            WHERE status='queued'
            ORDER BY priority DESC, id ASC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE tasks SET status='active' WHERE id=?",
            (row["id"],),
        )
        return dict(row)


def complete_task(task_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE tasks SET status='done', completed_at=? WHERE id=?",
            (utcnow(), task_id),
        )


def promote_version(version: str, score: float, path: str, notes: str = "", parent: str | None = None) -> None:
    with connect() as conn:
        conn.execute("UPDATE versions SET is_best=0")
        conn.execute(
            """
            INSERT INTO versions(version, parent_version, score, path, notes, is_best, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(version) DO UPDATE SET
                score=excluded.score,
                path=excluded.path,
                notes=excluded.notes,
                is_best=1
            """,
            (version, parent, score, path, notes, utcnow()),
        )


def best_version() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM versions WHERE is_best=1 ORDER BY score DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def recent_experiments(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def recent_failures(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM failures ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def counts() -> dict[str, int]:
    with connect() as conn:
        return {
            "experiments": conn.execute("SELECT COUNT(*) c FROM experiments").fetchone()["c"],
            "candidates": conn.execute("SELECT COUNT(*) c FROM candidates").fetchone()["c"],
            "versions": conn.execute("SELECT COUNT(*) c FROM versions").fetchone()["c"],
            "failures": conn.execute("SELECT COUNT(*) c FROM failures").fetchone()["c"],
            "tasks_queued": conn.execute(
                "SELECT COUNT(*) c FROM tasks WHERE status='queued'"
            ).fetchone()["c"],
        }
