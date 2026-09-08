"""Multi-template + AutoCut-preset tournament on the 1000-clip library.

Hard gate: refuse to run if unique source videos < 200 (forces pool rebuild).
Decision uses comparable ≤42s templates vs V4 emotional 8.36.
"""

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
from wedding_v3.shots import build_library_pool, load_pool  # noqa: E402

OUT = ROOT / "Output" / "autolab" / "craft_tournament"
CACHE_POOL = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"
AUD_DIR = ROOT / "resource" / "audio" / "wedding_web"
BASELINE_BEST = 8.36
MIN_UNIQUE_VIDEOS = 200


def _pool_stats(shots) -> dict:
    videos = {Path(s.video).resolve().as_posix().lower() for s in shots}
    emos = [float(s.emotion_score or 0) for s in shots]
    return {
        "n_shots": len(shots),
        "n_videos": len(videos),
        "mean_emotion": round(sum(emos) / max(1, len(emos)), 4),
        "peak_emotion": round(max(emos) if emos else 0.0, 4),
    }


def _ensure_pool(force_rebuild: bool = False):
    shots = []
    if CACHE_POOL.exists() and not force_rebuild:
        shots = load_pool(CACHE_POOL)
    stats = _pool_stats(shots) if shots else {"n_shots": 0, "n_videos": 0}
    print(f"pool check: {stats}", flush=True)
    if stats.get("n_videos", 0) < MIN_UNIQUE_VIDEOS:
        print(
            f"pool too small ({stats.get('n_videos', 0)} videos < {MIN_UNIQUE_VIDEOS}); "
            "rebuilding library pool...",
            flush=True,
        )
        shots = build_library_pool(force=False)
        stats = _pool_stats(shots)
        print(f"pool after rebuild: {stats}", flush=True)
    if stats.get("n_videos", 0) < MIN_UNIQUE_VIDEOS:
        raise SystemExit(
            f"abort: still only {stats.get('n_videos')} unique videos "
            f"(need >= {MIN_UNIQUE_VIDEOS}). Wait for full 1000-clip analyze."
        )
    return shots, stats


def _decide(board: list[dict], craft_list: list[dict]) -> dict:
    dur_by_id = {t.get("id"): float(t.get("target_duration") or 38) for t in craft_list}
    comparable = []
    longform = []
    for row in board:
        dur = dur_by_id.get(row.get("craft_id"), 38.0)
        row2 = {**row, "target_duration": dur}
        if dur <= 42:
            comparable.append(row2)
        else:
            longform.append(row2)
    comparable.sort(key=lambda r: r["overall"], reverse=True)
    longform.sort(key=lambda r: r["overall"], reverse=True)
    best_c = comparable[0] if comparable else None
    score = float(best_c["overall"]) if best_c else 0.0
    if score >= BASELINE_BEST + 0.25:
        decision = "KEEP_CANDIDATE"
    elif score >= BASELINE_BEST:
        decision = "HOLD_NEAR"
    else:
        decision = "REJECT"
    return {
        "decision": decision,
        "best_comparable": best_c,
        "best_longform": longform[0] if longform else None,
        "comparable_top5": comparable[:5],
        "social_teaser_best": next(
            (r for r in comparable if (r.get("craft_id") or "").startswith("social_")),
            None,
        ),
        "highlight_best": next(
            (r for r in longform if "highlight" in (r.get("craft_id") or "")),
            None,
        ),
        "autocut_best": next(
            (
                r
                for r in (comparable + longform)
                if (r.get("craft_id") or "").startswith("autocut_")
            ),
            None,
        ),
    }


def main() -> None:
    os.environ.setdefault("WEDDING_V3_PACE_HOLD", "1")
    os.environ.setdefault("WEDDING_V3_PEAK_HOLD", "1")
    os.environ.setdefault("WEDDING_V3_MUSIC_SECTION_ROLES", "1")
    os.environ.setdefault("WEDDING_V3_COLOR_CONTINUITY", "1")
    os.environ.setdefault("WEDDING_V3_CRAFT_SHOTS", "1")
    os.environ.setdefault("WEDDING_V3_PHRASE_SYNC", "1")

    shots, pool_stats = _ensure_pool()
    craft_list = all_craft()
    print(
        f"craft packs templates={list_templates()} presets={list_presets()} "
        f"total={len(craft_list)}",
        flush=True,
    )

    audios = [
        AUD_DIR / "music_428.mp3",
        AUD_DIR / "music_698.mp3",
    ]
    audios = [a for a in audios if a.exists()]
    if not audios:
        raise SystemExit("no wedding_web music tracks found")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    all_results = []
    for audio in audios:
        tag = f"capcut1000_{audio.stem}_{ts}"
        print(f"\n=== Tournament {audio.name} ===", flush=True)
        # Plan all craft; render top comparable later via selective second pass if needed.
        summary = run_candidates(
            audio.resolve(),
            shots=shots,
            craft_templates=craft_list,
            render_top=3,
            tag=tag,
            out_root=OUT.resolve(),
        )
        board = summary.get("leaderboard") or []
        verdict = _decide(board, craft_list)
        result = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "audio": str(audio),
            "pool": pool_stats,
            "n_craft": len(craft_list),
            "baseline_best": BASELINE_BEST,
            "winner_raw": board[0] if board else None,
            **verdict,
            "leaderboard": board[:20],
            "rendered": summary.get("rendered"),
            "run_dir": str(OUT / tag),
            "notes": (
                "KEEP uses ≤42s comparable craft vs V4 8.36. "
                "Phrase sync + AutoCut presets enabled. Human watch before promote."
            ),
        }
        OUT.mkdir(parents=True, exist_ok=True)
        out_path = OUT / f"{tag}_decision.json"
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        all_results.append(result)
        print(json.dumps(result, indent=2), flush=True)
        print(
            f"DECISION={result['decision']} "
            f"comparable={(result['best_comparable'] or {}).get('overall', 0):.2f}",
            flush=True,
        )

    final = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pool": pool_stats,
        "results": [
            {
                "audio": Path(r["audio"]).name,
                "decision": r["decision"],
                "best_comparable": r.get("best_comparable"),
                "best_longform": r.get("best_longform"),
                "social_teaser_best": r.get("social_teaser_best"),
                "highlight_best": r.get("highlight_best"),
                "autocut_best": r.get("autocut_best"),
            }
            for r in all_results
        ],
    }
    (OUT / "CAPCUT1000_FINAL.json").write_text(json.dumps(final, indent=2), encoding="utf-8")
    print("WROTE", OUT / "CAPCUT1000_FINAL.json", flush=True)


if __name__ == "__main__":
    main()
