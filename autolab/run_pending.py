"""Execute pending AutoLab pipeline jobs (no Cursor Agent shell required).

Supervisor and humans can run:
  .\\.venv\\Scripts\\python.exe autolab\\run_pending.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PENDING = Path(__file__).resolve().parent / "pending_jobs.json"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "autolab" / "results" / "session_logs" / "pending_jobs.log"


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load() -> list[dict]:
    if not PENDING.exists():
        return []
    return json.loads(PENDING.read_text(encoding="utf-8"))


def _save(jobs: list[dict]) -> None:
    PENDING.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def _done(jobs: list[dict], job_id: str) -> bool:
    for j in jobs:
        if j.get("id") == job_id and j.get("status") == "done":
            return True
    return False


def main() -> int:
    py = str(VENV_PY if VENV_PY.exists() else sys.executable)
    jobs = _load()
    if not jobs:
        _log("No pending jobs.")
        return 0

    # Sort by priority
    ordered = sorted(jobs, key=lambda j: float(j.get("priority", 99)))
    ran = 0
    for job in ordered:
        if job.get("status") != "pending":
            continue
        dep = job.get("depends_on")
        if dep and not _done(jobs, dep):
            # Allow running if dependency failed/rejected — still want data —
            # but skip if dependency still pending.
            dep_job = next((j for j in jobs if j.get("id") == dep), None)
            if dep_job and dep_job.get("status") == "pending":
                _log(f"Skip {job['id']}: waiting on {dep}")
                continue

        script = ROOT / job["script"]
        if not script.exists():
            job["status"] = "failed"
            job["error"] = f"missing script {script}"
            _save(jobs)
            _log(f"FAILED {job['id']}: missing {script}")
            continue

        _log(f"START {job['id']} -> {script}")
        job["status"] = "running"
        job["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _save(jobs)

        proc = subprocess.run(
            [py, str(script)],
            cwd=str(ROOT),
            check=False,
        )
        job["returncode"] = proc.returncode
        job["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        job["status"] = "done" if proc.returncode == 0 else "failed"
        _save(jobs)
        _log(f"END {job['id']} status={job['status']} code={proc.returncode}")
        ran += 1

    _log(f"Pending runner finished. jobs_run={ran}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
