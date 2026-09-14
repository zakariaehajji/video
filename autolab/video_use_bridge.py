"""Thin bridge from wedding AutoLab to browser-use/video-use helpers.

video-use is speech-first (ElevenLabs Scribe). For Mixkit music montages we
mostly use timeline_view self-eval + optional grade presets — not full
transcript cutting.

Usage:
  python autolab/video_use_bridge.py timeline Output/autolab/highlight_4min/wedding_4min_resume.mp4
  python autolab/video_use_bridge.py grade-analyze Output/autolab/highlight_4min/wedding_4min_resume.mp4
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO_USE = Path.home() / "Developer" / "video-use"
HELPERS = VIDEO_USE / "helpers"


def _py() -> str:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return str(venv if venv.exists() else sys.executable)


def _run(script: str, args: list[str]) -> int:
    path = HELPERS / script
    if not path.exists():
        raise SystemExit(f"missing video-use helper: {path} (clone https://github.com/browser-use/video-use)")
    cmd = [_py(), str(path), *args]
    print(" ", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def cmd_timeline(video: Path, windows: list[tuple[float, float]]) -> None:
    out_dir = video.parent / "edit" / "verify"
    out_dir.mkdir(parents=True, exist_ok=True)
    for start, end in windows:
        out = out_dir / f"tv_{int(start):03d}_{int(end):03d}.png"
        rc = _run(
            "timeline_view.py",
            [str(video), str(start), str(end), "-o", str(out), "--n-frames", "8"],
        )
        if rc != 0:
            raise SystemExit(rc)
        print(f"wrote {out}", flush=True)


def cmd_grade_analyze(video: Path) -> None:
    raise SystemExit(_run("grade.py", ["--analyze", str(video)]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Bridge to video-use helpers")
    ap.add_argument("command", choices=("timeline", "grade-analyze"))
    ap.add_argument("video", type=Path)
    args = ap.parse_args()
    video = args.video if args.video.is_absolute() else ROOT / args.video
    if not video.exists():
        raise SystemExit(f"missing video: {video}")

    if args.command == "timeline":
        # Default: intro, mid story, late, outro — cut-boundary style windows.
        cmd_timeline(
            video,
            # Cap end slightly under duration — ffmpeg frame extract at EOF can fail.
            [(0, 4), (55, 65), (115, 125), (175, 185), (228, 239.5)],
        )
    elif args.command == "grade-analyze":
        cmd_grade_analyze(video)


if __name__ == "__main__":
    main()
