"""Render wedding-only 4min highlight resume (delivery pack)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Delivery gates for this film only.
os.environ.setdefault("WEDDING_V3_WEDDING_ONLY", "1")
os.environ.setdefault("WEDDING_V3_ORIENTATION", "landscape")
os.environ.setdefault("WEDDING_V3_FRAME_FILL", "1")
os.environ.setdefault("WEDDING_V3_STORY_PHASES", "1")
os.environ.setdefault("WEDDING_V3_PACE_HOLD", "1")
os.environ.setdefault("WEDDING_V3_PEAK_HOLD", "1")
os.environ.setdefault("WEDDING_V3_MUSIC_SECTION_ROLES", "1")
os.environ.setdefault("WEDDING_V3_COLOR_CONTINUITY", "1")
os.environ.setdefault("WEDDING_V3_PHRASE_SYNC", "1")
os.environ.setdefault("WEDDING_V3_CRAFT_SHOTS", "1")
os.environ.setdefault("WEDDING_V3_COLOR_MATCH", "1")
os.environ.setdefault("WEDDING_V3_KISS_ENSURE_SWAP", "1")
os.environ.setdefault("WEDDING_V3_KISS_CLIMAX_REPOSITION", "1")
os.environ.setdefault("WEDDING_V3_KISS_HOLD", "1")
os.environ.setdefault("WEDDING_V3_CEREMONY_NARRATIVE", "1")
os.environ.setdefault("WEDDING_V3_TITLE_CARDS", "1")

from autolab.craft import load_template
from wedding_v3.pipeline import run_candidates
from wedding_v3.shots import Shot, load_pool


def _absolutize(shots: list[Shot]) -> list[Shot]:
    out = []
    for s in shots:
        p = Path(s.video)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            # try library / wedding_web by name
            for base in (
                ROOT / "resource" / "video" / "library",
                ROOT / "resource" / "video" / "wedding_web",
            ):
                hits = list(base.rglob(Path(s.video).name))
                if hits:
                    p = hits[0]
                    break
        d = s.to_dict()
        d["video"] = str(p)
        out.append(Shot.from_dict(d))
    return out


def main() -> None:
    audio = ROOT / "resource" / "audio" / "wedding_web" / "music_4min_bed.mp3"
    if not audio.exists():
        raise SystemExit(f"missing audio bed: {audio}")
    craft = load_template("highlight_4min")
    shots = _absolutize(load_pool())
    print(f"pool loaded: {len(shots)} shots", flush=True)
    out_root = ROOT / "Output" / "autolab" / "highlight_4min"
    tag = "wedding_4min_v11_deny"
    result = run_candidates(
        audio,
        shots=shots,
        craft_templates=[craft],
        styles=[],
        profiles=[],
        render_top=1,
        tag=tag,
        out_root=out_root,
    )
    best = (result or {}).get("best") or {}
    src = Path(best.get("path") or "")
    deliver = out_root / "wedding_4min_resume.mp4"
    if src.exists():
        # Probe; copy as deliverable (no freeze pad).
        p = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(src),
            ],
            capture_output=True,
            text=True,
        )
        dur = float((p.stdout or "0").strip() or 0)
        print(f"best duration={dur:.2f}s overall={best.get('overall')} path={src}", flush=True)
        shutil.copy2(src, deliver)
        print(f"delivered → {deliver}", flush=True)
    else:
        raise SystemExit("no best candidate rendered")


if __name__ == "__main__":
    main()
