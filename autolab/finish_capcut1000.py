"""Finish CapCut1000: assemble pool from caches + lean tournament. No full rescan."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autolab.craft import all_craft, list_presets, list_templates  # noqa: E402
from wedding_v3.pipeline import run_candidates  # noqa: E402
from wedding_v3.shots import CACHE_DIR, Shot  # noqa: E402

OUT = ROOT / "Output" / "autolab" / "craft_tournament"
AUDIO = ROOT / "resource" / "audio" / "wedding_web" / "music_428.mp3"
BASELINE = 8.36


def assemble_pool():
    shots = []
    seen = set()
    for p in sorted(CACHE_DIR.glob("*.json")):
        if p.name == "pool.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for x in data:
            s = Shot.from_dict(x)
            if s.id in seen:
                continue
            seen.add(s.id)
            # absolute paths for ffmpeg
            vp = Path(s.video)
            if not vp.is_absolute():
                s.video = str((ROOT / vp).resolve())
            shots.append(s)
    pool_path = CACHE_DIR / "pool.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pool_path.write_text(json.dumps([s.to_dict() for s in shots], indent=2), encoding="utf-8")
    vids = {Path(s.video).resolve().as_posix().lower() for s in shots}
    stats = {
        "n_shots": len(shots),
        "n_videos": len(vids),
        "mean_emotion": round(
            sum(float(s.emotion_score or 0) for s in shots) / max(1, len(shots)), 4
        ),
    }
    print(f"ASSEMBLED {stats} -> {pool_path}", flush=True)
    return shots, stats


def decide(board, craft_list):
    dur = {t.get("id"): float(t.get("target_duration") or 38) for t in craft_list}
    comparable = []
    longform = []
    for row in board:
        d = dur.get(row.get("craft_id"), 38.0)
        row2 = {**row, "target_duration": d}
        (comparable if d <= 42 else longform).append(row2)
    comparable.sort(key=lambda r: r["overall"], reverse=True)
    longform.sort(key=lambda r: r["overall"], reverse=True)
    best_c = comparable[0] if comparable else None
    score = float(best_c["overall"]) if best_c else 0.0
    if score >= BASELINE + 0.25:
        decision = "KEEP_CANDIDATE"
    elif score >= BASELINE:
        decision = "HOLD_NEAR"
    else:
        decision = "REJECT"
    return decision, best_c, longform[0] if longform else None, comparable[:5]


def main():
    os.environ["WEDDING_V3_PACE_HOLD"] = "1"
    os.environ["WEDDING_V3_PEAK_HOLD"] = "1"
    os.environ["WEDDING_V3_MUSIC_SECTION_ROLES"] = "1"
    os.environ["WEDDING_V3_COLOR_CONTINUITY"] = "1"
    os.environ["WEDDING_V3_CRAFT_SHOTS"] = "1"
    os.environ["WEDDING_V3_PHRASE_SYNC"] = "1"

    shots, stats = assemble_pool()
    if stats["n_videos"] < 200:
        raise SystemExit(f"not enough cached videos: {stats}")

    craft_list = all_craft()
    print(
        f"craft={len(craft_list)} templates={list_templates()} presets={list_presets()}",
        flush=True,
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = f"capcut1000_finish_{ts}"
    summary = run_candidates(
        AUDIO.resolve(),
        shots=shots,
        craft_templates=craft_list,
        render_top=2,
        tag=tag,
        out_root=OUT.resolve(),
    )
    board = summary.get("leaderboard") or []
    decision, best_c, best_l, top5 = decide(board, craft_list)
    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pool": stats,
        "n_craft": len(craft_list),
        "baseline": BASELINE,
        "decision": decision,
        "best_comparable": best_c,
        "best_longform": best_l,
        "comparable_top5": top5,
        "rendered": summary.get("rendered"),
        "run_dir": str(OUT / tag),
        "notes": "Finished from shot caches (partial 1000 analyze). Phrase sync + AutoCut presets. Stop after this.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{tag}_decision.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (OUT / "CAPCUT1000_FINAL.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    print(f"DONE decision={decision}", flush=True)


if __name__ == "__main__":
    main()
