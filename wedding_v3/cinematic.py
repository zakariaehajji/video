"""Cinematic rendering: context-aware slow-mo and crossfades."""

from __future__ import annotations

import subprocess
from pathlib import Path

from wedding_v3.ranking import RankedPick


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
            "-vf", f"fps=30,format=yuv420p,tpad=stop_mode=clone:stop_duration=0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
            "-an", str(exact),
        ])
        parts.append(exact)

    # Prefer concat for reliability; selective xfade between soft beats
    if use_xfade and len(parts) >= 3:
        # Only xfade pairs where planned; otherwise concat chain in groups
        # Simpler robust approach: concat demuxer (hard cuts) + short fade on soft picks via fade filter baked in extract
        for i, pick in enumerate(picks):
            if pick.beat.want_xfade and i > 0:
                faded = work / f"{i:03d}_fade.mp4"
                run([
                    "ffmpeg", "-y", "-i", str(parts[i]),
                    "-vf", "fade=t=in:st=0:d=0.25,fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                    str(faded),
                ])
                parts[i] = faded

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = work / "silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])

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
