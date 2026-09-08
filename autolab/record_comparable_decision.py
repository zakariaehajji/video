"""Honest post-pass on craft tournament: comparable (<=42s) vs long-form winners."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOUR = ROOT / "Output" / "autolab" / "craft_tournament"
TEMPL = ROOT / "autolab" / "craft" / "templates"
BASELINE = 8.36


def main() -> None:
    runs = sorted(TOUR.glob("craft_tour_*_decision.json"))
    if not runs:
        # find from run dirs
        for d in sorted(TOUR.glob("craft_tour_*")):
            lb = d / "leaderboard.json"
            if lb.exists():
                summary = json.loads(lb.read_text(encoding="utf-8"))
                break
        else:
            raise SystemExit("no tournament output")
    else:
        decision = json.loads(runs[-1].read_text(encoding="utf-8"))
        summary = {
            "leaderboard": decision.get("leaderboard") or [],
            "rendered": decision.get("rendered"),
        }
        dpath = runs[-1]

    dur_by_id = {}
    for p in TEMPL.glob("*.json"):
        t = json.loads(p.read_text(encoding="utf-8"))
        dur_by_id[t.get("id")] = float(t.get("target_duration") or 38)

    board = summary.get("leaderboard") or []
    comparable = []
    longform = []
    for row in board:
        cid = row.get("craft_id")
        dur = dur_by_id.get(cid, 38)
        row2 = dict(row)
        row2["target_duration"] = dur
        if dur <= 42:
            comparable.append(row2)
        else:
            longform.append(row2)

    comparable.sort(key=lambda r: r["overall"], reverse=True)
    longform.sort(key=lambda r: r["overall"], reverse=True)
    best_c = comparable[0] if comparable else None
    best_l = longform[0] if longform else None
    score = float(best_c["overall"]) if best_c else 0.0
    if score >= BASELINE + 0.25:
        decision_label = "KEEP_CANDIDATE"
    elif score >= BASELINE:
        decision_label = "HOLD_NEAR"
    else:
        decision_label = "REJECT"

    out = {
        "baseline_best_v4_emotional": BASELINE,
        "best_comparable_le_42s": best_c,
        "best_longform": best_l,
        "decision_comparable": decision_label,
        "caveat": (
            "Long templates (60s/90s) can inflate critic overall via shot count/variety; "
            "promote only after human watch of comparable-length renders. "
            "Auto critic >> human baseline gap remains a known weakness."
        ),
        "comparable_top5": comparable[:5],
    }
    out_path = TOUR / "comparable_decision.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"COMPARABLE_DECISION={decision_label} score={score:.2f}")


if __name__ == "__main__":
    main()
