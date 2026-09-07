"""v3: tighter face crop, sharper grade, punchier energy cuts."""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parent
VIDEO = ROOT / "resource" / "video" / "videoplayback.mp4"
AUDIO = ROOT / "resource" / "audio" / "babydoll.mp3"
WORK = ROOT / "Output" / "preview_v3_build"
OUTPUT = ROOT / "Output" / "babydoll_bilal_FIRE.mp4"

# Tighter face window: cut bottom Kick banner + right chat
CROP_H = 300
CROP_W = int(CROP_H * 9 / 16)  # 168
CROP_Y = 18
FACE_X = 232  # face center in 640 frame
OUT_W, OUT_H = 1080, 1920

VIDEO_POOL_START = 25.0
VIDEO_POOL_END = 1500.0
MIN_GAP = 3.0


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "fail")[-2500:])


def analyze_music(audio_path: Path) -> list[dict]:
    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).astype(float)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr)
    win = max(8, int(0.3 * sr / 512))
    energy = np.convolve(onset_env, np.ones(win) / win, mode="same")
    energy = (energy - energy.min()) / (energy.max() - energy.min() + 1e-8)

    # Also detect local peaks for extra punch cuts
    peaks = librosa.util.peak_pick(onset_env, pre_max=3, post_max=3, pre_avg=3, post_avg=5, delta=0.15, wait=5)
    peak_times = set(float(round(t, 2)) for t in times[peaks])

    cuts = [0.0]
    i = 0
    while i < len(beat_times):
        t = float(beat_times[i])
        idx = min(int(np.searchsorted(times, t)), len(energy) - 1)
        e = float(energy[idx])
        if e > 0.78:
            step, lo, hi = 1, 0.32, 0.70
        elif e > 0.55:
            step, lo, hi = 2, 0.45, 1.05
        else:
            step, lo, hi = 3, 0.70, 1.55
        nxt_i = min(i + step, len(beat_times) - 1)
        shot = float(np.clip(beat_times[nxt_i] - t, lo, hi))
        end = min(duration, t + shot)
        if end - cuts[-1] >= 0.28:
            cuts.append(end)
        i += max(1, step)
    if cuts[-1] < duration:
        cuts.append(duration)

    cleaned = [cuts[0]]
    for c in cuts[1:]:
        if c - cleaned[-1] >= 0.28:
            cleaned.append(c)
    cleaned[-1] = duration

    segs = []
    for a, b in zip(cleaned[:-1], cleaned[1:]):
        mid = (a + b) / 2
        idx = min(int(np.searchsorted(times, mid)), len(energy) - 1)
        e = float(energy[idx])
        near_peak = any(abs(a - p) < 0.12 for p in peak_times)
        segs.append({
            "start": a, "end": b, "dur": b - a, "energy": e,
            "punch": bool(near_peak or e > 0.72),
        })
    print(f"  tempo~{float(np.atleast_1d(tempo)[0]):.1f} BPM  segs={len(segs)}")
    return segs


def assign(segs: list[dict], rng: random.Random) -> list[dict]:
    span = VIDEO_POOL_END - VIDEO_POOL_START
    pool = []
    for i in range(len(segs) * 4):
        g = (i * 0.6180339887 + rng.random() * 0.07) % 1.0
        # bias a bit to first 12 minutes where energy/reactions tend to be denser
        bias = g ** 0.85
        pool.append(VIDEO_POOL_START + bias * span)
    used = []
    out = []
    for seg in segs:
        best = None
        best_score = -1e9
        for t in pool:
            gap = min((abs(t - u) for u in used), default=999)
            if gap < MIN_GAP:
                continue
            # prefer unused regions + mild energy mapping
            score = gap + rng.random() * 2
            if score > best_score:
                best_score, best = score, t
        if best is None:
            best = rng.uniform(VIDEO_POOL_START, VIDEO_POOL_END - 2)
        used.append(best)
        out.append({**seg, "vstart": float(best)})
    return out


def vf(seg: dict, i: int) -> str:
    jx = int((hashlib.md5(f"{i}:{seg['vstart']}".encode()).digest()[0] % 17) - 8)
    cx = int(np.clip(FACE_X - CROP_W // 2 + jx, 0, 640 - CROP_W))
    cy = CROP_Y
    # grade + sharpen (helps 360p source)
    look = (
        "eq=contrast=1.22:saturation=1.28:brightness=0.035:gamma=0.92,"
        "unsharp=5:5:0.9:5:5:0.0"
    )
    base = f"crop={CROP_W}:{CROP_H}:{cx}:{cy},scale={OUT_W}:{OUT_H}:flags=lanczos,{look}"
    if seg["punch"] or seg["energy"] > 0.68:
        frames = max(10, int(seg["dur"] * 30))
        # punch zoom + white flash
        return (
            f"{base},"
            f"zoompan=z='min(1.12,1+0.12*on/{max(frames//2,1)})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={OUT_W}x{OUT_H}:fps=30,"
            f"fade=t=in:st=0:d=0.05:color=white,format=yuv420p"
        )
    return f"{base},fps=30,format=yuv420p"


def render(plan: list[dict]) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, seg in enumerate(plan):
        part = WORK / f"c_{i:04d}.mp4"
        print(f"  [{i+1}/{len(plan)}] {seg['dur']:.2f}s  v@{seg['vstart']:.1f}  e={seg['energy']:.2f} punch={seg['punch']}")
        run([
            "ffmpeg", "-y", "-ss", f"{seg['vstart']:.3f}", "-i", str(VIDEO),
            "-t", f"{seg['dur']:.3f}", "-an",
            "-vf", vf(seg, i),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
            "-pix_fmt", "yuv420p", str(part),
        ])
        parts.append(part)

    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = WORK / "silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])
    run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(AUDIO),
        "-filter_complex", "[1:a]loudnorm=I=-13:TP=-1.2:LRA=10[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "17",
        "-c:a", "aac", "-b:a", "320k",
        "-shortest", "-movflags", "+faststart",
        str(OUTPUT),
    ])
    return OUTPUT


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    print("Analyzing music...")
    segs = analyze_music(AUDIO)
    plan = assign(segs, random.Random(7))
    (WORK / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print("Rendering v3 FIRE...")
    out = render(plan)
    print(f"Done: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
