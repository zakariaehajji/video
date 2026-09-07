import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STATE_DIR = ROOT / "autolab" / "state"
DB_PATH = STATE_DIR / "lab.db"

STATE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# MCP SERVER
# ============================================================

mcp = FastMCP("Wedding AI AutoLab")


# ============================================================
# DATABASE
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():

    conn = get_db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS lab_state (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS experiments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT UNIQUE,
        version TEXT,
        hypothesis TEXT,
        configuration TEXT,
        score REAL,
        status TEXT,
        result TEXT,
        runtime_seconds REAL,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT UNIQUE,
        title TEXT,
        description TEXT,
        priority INTEGER,
        status TEXT,
        created_at TEXT,
        completed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version TEXT UNIQUE,
        score REAL,
        path TEXT,
        notes TEXT,
        created_at TEXT
    );
    """)

    defaults = {
        "current_version": "V3",
        "best_version": "V3",
        "best_score": "7.6",
        "current_experiment": "initialization",
        "remaining_time": "0",
        "active_agents": "0",
        "failed_experiments": "0",
        "next_tasks": "[]",
    }

    for key, value in defaults.items():

        conn.execute(
            """
            INSERT OR IGNORE INTO lab_state
            (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (
                key,
                value,
                utc_now(),
            ),
        )

    conn.execute(
        """
        INSERT OR IGNORE INTO versions
        (version, score, path, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "V3",
            7.6,
            "Output/wedding_v3/BEST_v3.mp4",
            "Current baseline",
            utc_now(),
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# STATE HELPERS
# ============================================================

def read_state() -> dict[str, Any]:

    initialize_database()

    conn = get_db()

    rows = conn.execute(
        "SELECT key, value FROM lab_state"
    ).fetchall()

    state = {}

    for row in rows:

        key = row["key"]
        value = row["value"]

        if key == "best_score":

            try:
                value = float(value)
            except Exception:
                pass

        elif key == "next_tasks":

            try:
                value = json.loads(value)
            except Exception:
                value = []

        state[key] = value

    conn.close()

    return state


def write_state(key: str, value: Any):

    initialize_database()

    conn = get_db()

    if isinstance(value, (dict, list)):
        value = json.dumps(value)

    conn.execute(
        """
        INSERT INTO lab_state
        (key, value, updated_at)
        VALUES (?, ?, ?)

        ON CONFLICT(key)
        DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (
            key,
            str(value),
            utc_now(),
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# MCP TOOLS
# ============================================================

@mcp.tool()
def get_lab_status() -> dict:
    """
    Return the complete current AutoLab state.

    Includes current version, best version, best score,
    current experiment, remaining time, active agents,
    failed experiments, tasks and experiment counts.
    """

    initialize_database()

    state = read_state()

    conn = get_db()

    experiment_count = conn.execute(
        "SELECT COUNT(*) FROM experiments"
    ).fetchone()[0]

    version_count = conn.execute(
        "SELECT COUNT(*) FROM versions"
    ).fetchone()[0]

    task_count = conn.execute(
        "SELECT COUNT(*) FROM tasks"
    ).fetchone()[0]

    active_task_count = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status = 'RUNNING'"
    ).fetchone()[0]

    conn.close()

    state["experiment_count"] = experiment_count
    state["version_count"] = version_count
    state["task_count"] = task_count
    state["active_task_count"] = active_task_count

    return state


@mcp.tool()
def update_lab_state(
    key: str,
    value: str,
) -> dict:
    """
    Update one AutoLab state value.
    """

    write_state(key, value)

    return {
        "success": True,
        "key": key,
        "value": value,
    }


@mcp.tool()
def add_task(
    task_id: str,
    title: str,
    description: str,
    priority: int = 5,
) -> dict:
    """
    Add a research task to the AutoLab queue.
    """

    initialize_database()

    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO tasks
        (
            task_id,
            title,
            description,
            priority,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            title,
            description,
            priority,
            "TODO",
            utc_now(),
        ),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "task_id": task_id,
        "status": "TODO",
    }


@mcp.tool()
def get_next_tasks(limit: int = 10) -> list:
    """
    Return highest-priority unfinished research tasks.
    """

    initialize_database()

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            task_id,
            title,
            description,
            priority,
            status,
            created_at
        FROM tasks

        WHERE status IN ('TODO', 'READY')

        ORDER BY priority DESC, id ASC

        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


@mcp.tool()
def start_task(task_id: str) -> dict:
    """
    Mark a research task as RUNNING.
    """

    initialize_database()

    conn = get_db()

    cursor = conn.execute(
        """
        UPDATE tasks
        SET status = 'RUNNING'
        WHERE task_id = ?
        """,
        (task_id,),
    )

    conn.commit()
    conn.close()

    return {
        "success": cursor.rowcount > 0,
        "task_id": task_id,
        "status": "RUNNING",
    }


@mcp.tool()
def complete_task(
    task_id: str,
    result: str = "",
) -> dict:
    """
    Mark a research task as completed.
    """

    initialize_database()

    conn = get_db()

    cursor = conn.execute(
        """
        UPDATE tasks
        SET
            status = 'DONE',
            completed_at = ?
        WHERE task_id = ?
        """,
        (
            utc_now(),
            task_id,
        ),
    )

    conn.commit()
    conn.close()

    return {
        "success": cursor.rowcount > 0,
        "task_id": task_id,
        "status": "DONE",
        "result": result,
    }


@mcp.tool()
def record_experiment(
    experiment_id: str,
    version: str,
    hypothesis: str,
    configuration: str,
    score: float,
    status: str,
    result: str,
    runtime_seconds: float = 0,
) -> dict:
    """
    Record a completed or failed experiment.
    """

    initialize_database()

    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO experiments
        (
            experiment_id,
            version,
            hypothesis,
            configuration,
            score,
            status,
            result,
            runtime_seconds,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            experiment_id,
            version,
            hypothesis,
            configuration,
            score,
            status,
            result,
            runtime_seconds,
            utc_now(),
        ),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "experiment_id": experiment_id,
        "version": version,
        "score": score,
        "status": status,
    }


@mcp.tool()
def register_version(
    version: str,
    score: float,
    path: str,
    notes: str = "",
) -> dict:
    """
    Register a new version of the wedding editor.
    """

    initialize_database()

    conn = get_db()

    conn.execute(
        """
        INSERT OR REPLACE INTO versions
        (
            version,
            score,
            path,
            notes,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            version,
            score,
            path,
            notes,
            utc_now(),
        ),
    )

    conn.commit()
    conn.close()

    state = read_state()

    best_score = float(state.get("best_score", 0))

    if score > best_score:

        write_state("best_version", version)
        write_state("best_score", str(score))

    write_state("current_version", version)

    return {
        "success": True,
        "version": version,
        "score": score,
        "is_new_best": score > best_score,
    }


@mcp.tool()
def get_experiment_history(limit: int = 20) -> list:
    """
    Return recent experiment history.
    """

    initialize_database()

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            experiment_id,
            version,
            hypothesis,
            configuration,
            score,
            status,
            result,
            runtime_seconds,
            created_at

        FROM experiments

        ORDER BY id DESC

        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


@mcp.tool()
def get_version_history(limit: int = 20) -> list:
    """
    Return recent version history.
    """

    initialize_database()

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            version,
            score,
            path,
            notes,
            created_at

        FROM versions

        ORDER BY id DESC

        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# INITIALIZATION
# ============================================================

initialize_database()


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    # IMPORTANT:
    # MCP stdio owns stdout.
    # Never print normal logs to stdout.

    if "--status" in sys.argv:

        print(
            json.dumps(
                get_lab_status(),
                indent=2,
            )
        )

    else:

        mcp.run(
            transport="stdio"
        )
