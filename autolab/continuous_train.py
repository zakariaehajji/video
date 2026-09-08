"""Continuous AutoLab training loop — runs until killed (Ctrl+C / stop).

Cycles measurable wedding_v3 experiments with real renders + critic scores.
Does not invent results. Never overwrites Output/wedding_v3/BEST_v3.mp4.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "autolab" / "results" / "session_logs" / "continuous_train"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "train.log"
LEADERBOARD = LOG_DIR / "leaderboard.json"

# Existing one-shot experiment runners (real renders).
EXPERIMENTS = [
    "autolab/run_v5_pacing.py",
    "autolab/run_v11_peak_hold.py",
    "autolab/run_v4_xfade.py",
    "autolab/run_v10_continuity.py",
    "autolab/run_v9_visual.py",
    "autolab/run_v6_emotion.py",
    "autolab/run_v7_titles.py",
    "autolab/run_v8_tears.py",
]


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_board() -> list[dict]:
    if LEADERBOARD.exists():
        try:
            return json.loads(LEADERBOARD.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_board(board: list[dict]) -> None:
    LEADERBOARD.write_text(json.dumps(board, indent=2), encoding="utf-8")


def collect_evals() -> list[dict]:
    rows = []
    base = ROOT / "Output" / "autolab"
    if not base.exists():
        return rows
    for path in base.rglob("EVAL.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_eval_path"] = str(path)
            rows.append(data)
        except Exception:
            pass
    return rows


def run_one(script: str, round_id: int) -> int:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    cmd = [str(py), str(ROOT / script)]
    log(f"ROUND {round_id} START {script}")
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45 * 60,
        )
        dur = time.time() - t0
        out_tail = (proc.stdout or "")[-2000:]
        err_tail = (proc.stderr or "")[-1000:]
        log(f"ROUND {round_id} EXIT code={proc.returncode} duration={dur:.1f}s")
        if out_tail.strip():
            log(f"STDOUT tail:\n{out_tail}")
        if proc.returncode != 0 and err_tail.strip():
            log(f"STDERR tail:\n{err_tail}")
        return proc.returncode
    except subprocess.TimeoutExpired:
        log(f"ROUND {round_id} TIMEOUT {script}")
        return 124
    except Exception as e:
        log(f"ROUND {round_id} ERROR {e}")
        return 1


def summarize() -> None:
    rows = collect_evals()
    scored = []
    for r in rows:
        score = r.get("best_score") or r.get("score")
        if score is None and isinstance(r.get("critique"), dict):
            score = r["critique"].get("overall")
        if score is None:
            continue
        scored.append(
            {
                "experiment": r.get("experiment") or r.get("_eval_path"),
                "score": float(score),
                "verdict": r.get("verdict"),
                "best": r.get("best"),
                "updated_at": r.get("updated_at"),
                "eval_path": r.get("_eval_path"),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    save_board(scored[:50])
    if scored:
        top = scored[0]
        log(
            f"BEST_SO_FAR score={top['score']} verdict={top.get('verdict')} "
            f"exp={top.get('experiment')}"
        )
    else:
        log("BEST_SO_FAR: none yet")


def main() -> None:
    log("========================================")
    log("CONTINUOUS TRAIN START — stop me when you want")
    log("========================================")
    round_id = 0
    while True:
        for script in EXPERIMENTS:
            if not (ROOT / script).exists():
                log(f"SKIP missing {script}")
                continue
            round_id += 1
            run_one(script, round_id)
            summarize()
            time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("STOPPED by user")
        summarize()
        sys.exit(0)
