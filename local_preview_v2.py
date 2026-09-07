"""Cinematic local beat-sync edit: vertical crop, energy pacing, diverse shots."""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parent
VIDEO = ROOT / "resource" / "video" / "videoplayback.mp4"
AUDIO = ROOT / "resource" / "audio" / "babydoll.mp3"
WORK = ROOT / "Output" / "preview_v2_build"
OUTPUT = ROOT / "Output" / "babydoll_bilal_FIRE.mp4"
CACHE = WORK / "plan.json"

# Source stream is 640x360 with chat on the right — crop left-center on Bilal.
CROP_W, CROP_H = 202, 360
CROP_X, CROP_Y = 170, 0
OUT_W, OUT_H = 720, 1280

VIDEO_POOL_START = 20.0
VIDEO_POOL_END = 1200.0  # first ~20 minutes
MIN_GAP_BETWEEN_USES = 2.5


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "fail")[-2500:])


def analyze_music(audio_path: Path) -> dict:
    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).astype(float)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)

    # Smooth energy curve 0..1
    win = max(8, int(sr / 512 * 0.35))
    kernel = np.ones(win) / win
    energy = np.convolve(onset_env, kernel, mode="same")
    energy = (energy - energy.min()) / (energy.max() - energy.min() + 1e-8)

    # Prefer downbeats every ~4 beats for section feel
    strong = set(int(round(t * 1000)) for t in beat_times[::4])

    cuts = [0.0]
    i = 0
    while i < len(beat_times):
        t = float(beat_times[i])
        # local energy around this beat
        idx = int(np.searchsorted(times, t))
        e = float(energy[min(idx, len(energy) - 1)])
        # high energy -> shorter shots (1 beat), low -> 2-3 beats
        if e > 0.72:
            step = 1
            shot = max(0.35, min(0.85, (beat_times[min(i + 1, len(beat_times) - 1)] - t) if i + 1 < len(beat_times) else 0.55))
        elif e > 0.45:
            step = 2
            nxt = beat_times[min(i + step, len(beat_times) - 1)]
            shot = float(nxt - t)
        else:
            step = 3
            nxt = beat_times[min(i + step, len(beat_times) - 1)]
            shot = float(nxt - t)

        shot = float(np.clip(shot, 0.35, 1.6))
        end = min(duration, t + shot)
        if end - cuts[-1] >= 0.32:
            cuts.append(end)
        i += max(1, step)

    if cuts[-1] < duration - 0.05:
        cuts.append(duration)

    # Deduplicate / clean
    cleaned = [cuts[0]]
    for c in cuts[1:]:
        if c - cleaned[-1] >= 0.30:
            cleaned.append(c)
    if cleaned[-1] < duration:
        cleaned[-1] = duration

    segments = []
    for a, b in zip(cleaned[:-1], cleaned[1:]):
        mid = (a + b) / 2
        idx = int(np.searchsorted(times, mid))
        e = float(energy[min(idx, len(energy) - 1)])
        is_strong = int(round(a * 1000)) in strong or e > 0.75
        segments.append({"start": a, "end": b, "dur": b - a, "energy": e, "punch": is_strong})

    return {
        "duration": duration,
        "tempo": float(np.atleast_1d(tempo)[0]),
        "segments": segments,
    }


def candidate_starts(n: int, rng: random.Random) -> list[float]:
    """Spread candidates across the stream pool with jitter."""
    span = VIDEO_POOL_END - VIDEO_POOL_START
    # denser early (more expressive open), still cover later
    pts = []
    for i in range(n):
        # mix uniform + golden-ratio scatter so we don't walk linearly
        g = (i * 0.6180339887) % 1.0
        base = VIDEO_POOL_START + g * span
        jitter = rng.uniform(-4.0, 4.0)
        t = float(np.clip(base + jitter, VIDEO_POOL_START, VIDEO_POOL_END - 2.0))
        pts.append(t)
    pts = sorted(set(round(p, 2) for p in pts))
    # ensure enough unique
    while len(pts) < n:
        pts.append(round(rng.uniform(VIDEO_POOL_START, VIDEO_POOL_END - 2.0), 2))
    return pts


def assign_video_clips(segments: list[dict], rng: random.Random) -> list[dict]:
    need = len(segments)
    pool = candidate_starts(need * 3, rng)
    used: list[float] = []
    assigned = []

    def pick(energy: float) -> float:
        # higher energy -> prefer later/random jumps for chaos; low energy calmer earlier pool
        ranked = sorted(
            pool,
            key=lambda t: (
                min(abs(t - u) for u in used) if used else 999,
                -abs(t - (VIDEO_POOL_START + energy * (VIDEO_POOL_END - VIDEO_POOL_START) * 0.6)),
            ),
            reverse=True,
        )
        for t in ranked:
            if all(abs(t - u) >= MIN_GAP_BETWEEN_USES for u in used):
                used.append(t)
                return t
        t = rng.uniform(VIDEO_POOL_START, VIDEO_POOL_END - 2.0)
        used.append(t)
        return t

    for seg in segments:
        vstart = pick(seg["energy"])
        assigned.append({**seg, "vstart": vstart})
    return assigned


def vf_for_clip(seg: dict, i: int) -> str:
    """Vertical crop + grade + optional beat punch zoom."""
    # slight crop jitter so shots don't feel locked
    jx = int((hashlib.md5(f"{i}-{seg['vstart']}".encode()).digest()[0] % 21) - 10)
    cx = int(np.clip(CROP_X + jx, 0, 640 - CROP_W))
    cy = CROP_Y

    grade = "eq=contrast=1.18:saturation=1.22:brightness=0.03:gamma=0.95"
    # punch zoom on strong beats
    if seg["punch"] or seg["energy"] > 0.7:
        # zoom from 1.0 -> 1.08 over the clip
        frames = max(8, int(seg["dur"] * 30))
        z = (
            f"zoompan=z='min(1.08,1+0.08*on/{frames})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={OUT_W}x{OUT_H}:fps=30"
        )
        return f"crop={CROP_W}:{CROP_H}:{cx}:{cy},scale={OUT_W}:{OUT_H}:flags=lanczos,{grade},{z},format=yuv420p"
    return (
        f"crop={CROP_W}:{CROP_H}:{cx}:{cy},"
        f"scale={OUT_W}:{OUT_H}:flags=lanczos,{grade},fps=30,format=yuv420p"
    )


def render(plan: list[dict]) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for i, seg in enumerate(plan):
        part = WORK / f"clip_{i:04d}.mp4"
        print(f"  [{i+1}/{len(plan)}] music {seg['start']:.2f}-{seg['end']:.2f}s  "
              f"v@{seg['vstart']:.1f}s  e={seg['energy']:.2f}  punch={seg['punch']}")
        vf = vf_for_clip(seg, i)
        # tiny white flash in on punches via fade
        fade = []
        if seg["punch"]:
            # 2-frame white flash feel via fade-in from white
            fade = ["-vf", vf + ",fade=t=in:st=0:d=0.06:color=white"]
        else:
            fade = ["-vf", vf]

        run([
            "ffmpeg", "-y",
            "-ss", f"{seg['vstart']:.3f}",
            "-i", str(VIDEO),
            "-t", f"{seg['dur']:.3f}",
            "-an",
            *fade,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(part),
        ])
        parts.append(part)

    concat_list = WORK / "concat.txt"
    concat_list.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = WORK / "silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(silent)])

    # Final mux + loudness-ish audio normalize lightly
    run([
        "ffmpeg", "-y",
        "-i", str(silent),
        "-i", str(AUDIO),
        "-filter_complex",
        "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "256k",
        "-shortest",
        "-movflags", "+faststart",
        str(OUTPUT),
    ])
    return OUTPUT


def main() -> int:
    if not VIDEO.exists() or not AUDIO.exists():
        print("Missing media", file=sys.stderr)
        return 1

    WORK.mkdir(parents=True, exist_ok=True)
    print("Analyzing Babydoll...")
    music = analyze_music(AUDIO)
    print(f"  tempo~{music['tempo']:.1f} BPM  segments={len(music['segments'])}  dur={music['duration']:.1f}s")

    rng = random.Random(42)
    plan = assign_video_clips(music["segments"], rng)
    CACHE.write_text(json.dumps({"tempo": music["tempo"], "plan": plan}, indent=2), encoding="utf-8")

    print("Rendering FIRE cut...")
    out = render(plan)
    print(f"Done: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
