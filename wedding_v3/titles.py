"""Soft opening/closing title cards for wedding montages (V7 experiment).

Gated by WEDDING_V3_TITLE_CARDS=1 so V3–V6 baselines stay unchanged.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# V7 experiment gate — default off.
TITLE_CARDS = os.environ.get("WEDDING_V3_TITLE_CARDS", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)

INTRO_DUR = 1.65
OUTRO_DUR = 1.95
TOTAL_TARGET = 38.0


def content_duration(total: float = TOTAL_TARGET) -> float:
    """Footage duration when soft title/outro cards bookend the film."""
    if not TITLE_CARDS:
        return total
    return max(28.0, total - INTRO_DUR - OUTRO_DUR)


def _fontfile_arg() -> str:
    candidates = [
        Path(r"C:\Windows\Fonts\georgia.ttf"),
        Path(r"C:\Windows\Fonts\GARA.TTF"),
        Path(r"C:\Windows\Fonts\times.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        Path("/System/Library/Fonts/Supplemental/Georgia.ttf"),
    ]
    for p in candidates:
        if p.exists():
            # ffmpeg drawtext wants escaped drive colon on Windows
            return p.as_posix().replace(":", "\\:")
    return ""


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "ffmpeg title-card fail")[-2500:])


def make_title_card(
    out: Path,
    *,
    line1: str,
    line2: str = "",
    duration: float,
    fade_in: float = 0.45,
    fade_out: float = 0.55,
) -> Path:
    """Render a soft black title card with elegant serif text."""
    out.parent.mkdir(parents=True, exist_ok=True)
    font = _fontfile_arg()
    t1 = line1.replace(":", "\\:").replace("'", "\\'")
    t2 = line2.replace(":", "\\:").replace("'", "\\'") if line2 else ""

    fade_out_start = max(0.1, duration - fade_out)
    y1 = "(h-text_h)/2-28" if t2 else "(h-text_h)/2"
    parts: list[str] = ["format=yuv420p"]
    font_opt = f"fontfile='{font}':" if font else ""
    parts.append(
        f"drawtext={font_opt}text='{t1}':fontsize=52:"
        f"fontcolor=0xf5f0e8:x=(w-text_w)/2:y={y1}:alpha=0.92"
    )
    if t2:
        parts.append(
            f"drawtext={font_opt}text='{t2}':fontsize=28:"
            f"fontcolor=0xd8d0c4:x=(w-text_w)/2:y=(h-text_h)/2+42:alpha=0.85"
        )
    parts.append(f"fade=t=in:st=0:d={fade_in:.3f}")
    parts.append(f"fade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}")
    vf = ",".join(parts)

    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0a0a0c:s=1280x720:d={duration:.3f}:r=30",
            "-vf",
            vf,
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out),
        ]
    )
    return out


def bookend_silent(silent: Path, work: Path) -> Path:
    """Prepend intro + append outro title cards around a silent montage."""
    if not TITLE_CARDS:
        return silent
    work.mkdir(parents=True, exist_ok=True)
    intro = make_title_card(
        work / "title_intro.mp4",
        line1="A Wedding Film",
        line2="Together",
        duration=INTRO_DUR,
        fade_in=0.35,
        fade_out=0.5,
    )
    outro = make_title_card(
        work / "title_outro.mp4",
        line1="The Beginning",
        line2="",
        duration=OUTRO_DUR,
        fade_in=0.4,
        fade_out=0.65,
    )
    lst = work / "title_bookend.txt"
    lst.write_text(
        f"file '{intro.as_posix()}'\n"
        f"file '{silent.as_posix()}'\n"
        f"file '{outro.as_posix()}'\n",
        encoding="utf-8",
    )
    out = work / "silent_titled.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c",
            "copy",
            str(out),
        ]
    )
    return out
