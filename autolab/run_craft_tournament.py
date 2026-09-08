"""Multi-template craft tournament on music_428 (+ optional audio).

Records keep/reject decisions by critic evidence vs current best.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autolab.craft import all_templates, list_templates  # noqa: E402
from wedding_v3.pipeline import run_candidates  # noqa: E402
from wedding_v3.shots import build_library_pool, load_pool  # noqa: E402

OUT = ROOT / "Output" / "autolab" / "craft_tournament"
CACHE_POOL = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
AUDIO = ROOT / "resource" / "audio" / "wedding_web" / "music_428.mp3"
# Known strong Autolab baselines (critic overall) for honest keep/reject.
BASELINE_BEST = 8.36  # V4 emotional KEEP reference from overnight lab


def main() -> None:
    # Enable craft-aligned story/ranking gates for tournament fairness.
    os.environ.setdefault("WEDDING_V3_PACE_HOLD", "1")
    os.environ.setdefault("WEDDING_V3_PEAK_HOLD", "1")
    os.environ.setdefault("WEDDING_V3_MUSIC_SECTION_ROLES", "1")
    os.environ.setdefault("WEDDING_V3_COLOR_CONTINUITY", "1")
    os.environ.setdefault("WEDDING_V3_CRAFT_SHOTS", "1")

    if not AUDIO.exists():
        raise SystemExit(f"missing audio: {AUDIO}")

    print("=== Rebuild / load library shot pool ===", flush=True)
    if CACHE_POOL.exists():
        shots = load_pool(CACHE_POOL)
        print(f"loaded pool shots={len(shots)}", flush=True)
        if len(shots) < 20:
            shots = build_library_pool(force=False)
    else:
        shots = build_library_pool(force=False)

    templates = all_templates()
    print(f"templates={len(templates)} ids={list_templates()}", flush=True)

    tag = f"craft_tour_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    summary = run_candidates(
        AUDIO,
        shots=shots,
        craft_templates=templates,
        render_top=2,
        tag=tag,
        out_root=OUT,
    )

    board = summary.get("leaderboard") or []
    best = board[0] if board else None
    best_score = float(best["overall"]) if best else 0.0
    decision = "KEEP" if best_score >= BASELINE_BEST else "REJECT"
    if best_score >= BASELINE_BEST - 0.15 and best_score < BASELINE_BEST:
        decision = "HOLD_NEAR"  # interesting but not promote over V4

    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "audio": str(AUDIO),
        "n_shots": len(shots),
        "n_templates": len(templates),
        "baseline_best": BASELINE_BEST,
        "winner": best,
        "decision": decision,
        "leaderboard": board[:15],
        "rendered": summary.get("rendered"),
        "run_dir": str(OUT / tag),
        "notes": (
            "KEEP only if critic overall beats overnight V4 emotional 8.36. "
            "Human-feel still required before promoting as editor default."
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / f"{tag}_decision.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    print(f"DECISION={decision} best={best_score:.2f} vs baseline={BASELINE_BEST}", flush=True)


if __name__ == "__main__":
    main()
