"""Local beat-sync preview that does not need cloud API keys."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parent
VIDEO = ROOT / "resource" / "video" / "videoplayback.mp4"
AUDIO = ROOT / "resource" / "audio" / "babydoll.mp3"
WORK = ROOT / "Output" / "preview_build"
OUTPUT = ROOT / "Output" / "babydoll_bilal_preview.mp4"

MIN_SHOT = 0.6
MAX_SHOT = 2.0
VIDEO_START = 30.0
VIDEO_WINDOW = 300.0


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2000:] if proc.stderr else f"Command failed: {cmd}")


def beat_boundaries(audio_path: Path) -> np.ndarray:
    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    _, frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    times = librosa.frames_to_time(frames, sr=sr)
    points = [0.0]
    for t in times:
        if t - points[-1] >= MIN_SHOT:
            points.append(float(t))
    if duration - points[-1] > 0.2:
        points.append(float(duration))
    if points[-1] < duration:
        points[-1] = float(duration)
    return np.array(points, dtype=float)


def clip_plan(bounds: np.ndarray) -> list[tuple[float, float]]:
    clips = []
    video_cursor = VIDEO_START
    for start, end in zip(bounds[:-1], bounds[1:]):
        dur = min(MAX_SHOT, max(MIN_SHOT, float(end - start)))
        if video_cursor + dur > VIDEO_START + VIDEO_WINDOW:
            video_cursor = VIDEO_START
        clips.append((video_cursor, dur))
        video_cursor += dur + 0.85
    return clips


def main() -> int:
    if not VIDEO.exists() or not AUDIO.exists():
        print("Missing video or audio in resource/", file=sys.stderr)
        return 1

    WORK.mkdir(parents=True, exist_ok=True)
    print("Detecting beats...")
    bounds = beat_boundaries(AUDIO)
    clips = clip_plan(bounds)
    print(f"Building {len(clips)} shots, song length {bounds[-1]:.1f}s")

    parts = []
    for i, (start, dur) in enumerate(clips):
        part = WORK / f"clip_{i:03d}.mp4"
        print(f"  clip {i + 1}/{len(clips)}  video@{start:.1f}s  {dur:.2f}s")
        run([
            "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(VIDEO),
            "-t", f"{dur:.3f}", "-an",
            "-vf", "scale=640:360,fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            str(part),
        ])
        parts.append(part)

    concat_list = WORK / "concat.txt"
    concat_list.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = WORK / "silent.mp4"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", str(silent),
    ])
    run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(AUDIO),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(OUTPUT),
    ])
    print(f"Done: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
