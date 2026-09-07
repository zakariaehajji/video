"""Cinematic rendering: context-aware slow-mo and real soft-section crossfades."""

from __future__ import annotations

import subprocess
from pathlib import Path

from wedding_v3.ranking import RankedPick
from wedding_v3.titles import TITLE_CARDS, bookend_silent


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "ffmpeg fail")[-2500:])


def _grade(role: str) -> str:
    if role == "detail":
        return "eq=contrast=1.12:saturation=1.16:brightness=0.03:gamma=0.96,unsharp=5:5:0.65:5:5:0.0"
    if role == "portrait":
        return "eq=contrast=1.1:saturation=1.14:brightness=0.04:gamma=0.97,unsharp=3:3:0.55:3:3:0.0"
    if role == "motion":
        return "eq=contrast=1.12:saturation=1.18:brightness=0.02:gamma=0.95"
    return "eq=contrast=1.08:saturation=1.1:brightness=0.035:gamma=0.98"


def extract_shot(pick: RankedPick, out: Path) -> Path:
    shot = pick.shot
    beat = pick.beat
    need = beat.dur
    # Prefer best emotional moment as center
    center = shot.best_t
    half = need / 2
    start = max(shot.start, center - half)
    if start + need > shot.end:
        start = max(shot.start, shot.end - need)
    start = max(0.0, start)
    # slow-mo: take less source time, setpts
    slow = beat.want_slowmo and shot.emotion_score >= 0.35
    src_dur = need * (0.55 if slow else 1.0)
    src_dur = min(src_dur, max(0.4, shot.end - start - 0.02))

    vf = (
        f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
        f"{_grade(beat.role)},fps=30,format=yuv420p"
    )
    if slow:
        vf = (
            f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
            f"{_grade(beat.role)},setpts=PTS/{0.55},fps=30,format=yuv420p"
        )
        # After setpts, trim to need via -t on output
    run([
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", shot.video,
        "-t", f"{src_dur:.3f}", "-an", "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
        "-t", f"{need:.3f}",
        str(out),
    ])
    return out


def _should_xfade(prev: RankedPick, curr: RankedPick) -> bool:
    """Real crossfade only on soft boundaries; hard cuts at peaks."""
    if curr.beat.is_peak or prev.beat.is_peak:
        return False
    soft_sections = ("intro", "outro", "build")
    # Intro/outro: dissolve if either beat planned an xfade (asymmetric soft edges OK).
    if prev.beat.section in soft_sections or curr.beat.section in soft_sections:
        return bool(prev.beat.want_xfade or curr.beat.want_xfade)
    return bool(curr.beat.want_xfade and prev.beat.want_xfade)


def _fade_duration(prev_dur: float, curr_dur: float) -> float:
    # Soft cinematic dissolve; keep short enough to preserve music sync feel
    return round(min(0.40, max(0.18, min(prev_dur, curr_dur) * 0.22)), 3)


def _concat_two(a: Path, b: Path, out: Path) -> None:
    lst = out.with_suffix(".txt")
    lst.write_text(
        f"file '{a.as_posix()}'\nfile '{b.as_posix()}'\n",
        encoding="utf-8",
    )
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c", "copy", str(out),
    ])


def _xfade_pair(a: Path, b: Path, out: Path, dur_a: float, fade: float) -> float:
    offset = max(0.05, dur_a - fade)
    run([
        "ffmpeg", "-y", "-i", str(a), "-i", str(b),
        "-filter_complex",
        f"[0:v][1:v]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f},"
        f"fps=30,format=yuv420p[v]",
        "-map", "[v]", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
        str(out),
    ])
    # Probe output duration via ffprobe would be ideal; estimate from math
    return dur_a  # updated by caller with b duration


def _probe_duration(path: Path) -> float:
    p = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "ffprobe fail")[-1500:])
    return float((p.stdout or "0").strip() or 0)


def _assemble_with_selective_xfade(
    picks: list[RankedPick],
    parts: list[Path],
    work: Path,
) -> Path:
    """Chain clips: real xfade on soft pairs, hard concat at peaks."""
    acc = parts[0]
    acc_dur = float(picks[0].beat.dur)
    for i in range(1, len(parts)):
        nxt = parts[i]
        out = work / f"chain_{i:03d}.mp4"
        if _should_xfade(picks[i - 1], picks[i]):
            fade = _fade_duration(float(picks[i - 1].beat.dur), float(picks[i].beat.dur))
            fade = min(fade, acc_dur * 0.45, float(picks[i].beat.dur) * 0.45)
            fade = max(0.12, fade)
            _xfade_pair(acc, nxt, out, acc_dur, fade)
            try:
                acc_dur = _probe_duration(out)
            except Exception:
                acc_dur = acc_dur + float(picks[i].beat.dur) - fade
        else:
            _concat_two(acc, nxt, out)
            try:
                acc_dur = _probe_duration(out)
            except Exception:
                acc_dur = acc_dur + float(picks[i].beat.dur)
        acc = out
    return acc


def render_montage(
    picks: list[RankedPick],
    audio: Path,
    out: Path,
    work: Path,
    use_xfade: bool = True,
) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for i, pick in enumerate(picks):
        part = work / f"{i:03d}_{pick.beat.role}.mp4"
        extract_shot(pick, part)
        # pad/trim exact duration for xfade stability
        exact = work / f"{i:03d}_exact.mp4"
        run([
            "ffmpeg", "-y", "-i", str(part),
            "-t", f"{pick.beat.dur:.3f}",
            "-vf", "fps=30,format=yuv420p,tpad=stop_mode=clone:stop_duration=0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
            "-an", str(exact),
        ])
        parts.append(exact)

    if use_xfade and len(parts) >= 2 and any(
        _should_xfade(picks[i - 1], picks[i]) for i in range(1, len(picks))
    ):
        silent = _assemble_with_selective_xfade(picks, parts, work)
    else:
        # Hard-cut concat (peaks / energetic / xfade disabled)
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        silent = work / "silent.mp4"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])

    # V7: soft title/outro cards bookend the silent cut (gated; default off).
    if TITLE_CARDS:
        silent = bookend_silent(silent, work / "titles")

    audio = Path(audio)
    out.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(audio),
        "-filter_complex", "[1:a]atrim=0:38,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "17",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(out),
    ])
    return out
