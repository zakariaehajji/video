"""Download free Mixkit wedding footage + romantic music, render 10 test edits."""

from __future__ import annotations

import json
import random
import subprocess
import urllib.request
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parent
VID_DIR = ROOT / "resource" / "video" / "wedding_web"
AUD_DIR = ROOT / "resource" / "audio" / "wedding_web"
OUT_DIR = ROOT / "Output" / "wedding_tests"
WORK = ROOT / "Output" / "wedding_tests_build"

VIDEO_IDS = [36171, 40597, 40596, 40591, 40601, 40599, 4829, 5206, 5183, 5223]
MUSIC_IDS = [493, 698, 461, 81, 428, 25, 30, 140]
HDRS = {"User-Agent": "Mozilla/5.0 CutClawWeddingTests/1.0"}


def download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 50_000:
        print(f"  skip {dest.name}", flush=True)
        return True
    print(f"  get {dest.name} ...", flush=True)
    try:
        req = urllib.request.Request(url, headers=HDRS)
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        print(f"  ok {dest.name} ({dest.stat().st_size // 1024} KB)", flush=True)
        return True
    except Exception as e:
        print(f"  FAIL {url}: {e}", flush=True)
        if dest.exists():
            dest.unlink()
        return False


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "fail")[-2000:])


def soft_segments(audio: Path, max_len: float = 45.0) -> list[dict]:
    y, sr = librosa.load(str(audio), sr=22050, mono=True)
    duration = min(float(librosa.get_duration(y=y, sr=sr)), max_len)
    y = y[: int(duration * sr)]
    _, frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beats = librosa.frames_to_time(frames, sr=sr).astype(float)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.frames_to_time(np.arange(len(onset)), sr=sr)
    energy = np.convolve(onset, np.ones(12) / 12, mode="same")
    energy = (energy - energy.min()) / (energy.max() - energy.min() + 1e-8)

    cuts = [0.0]
    i = 0
    while i < len(beats) and cuts[-1] < duration - 0.4:
        t = float(beats[i])
        if t <= cuts[-1]:
            i += 1
            continue
        idx = min(int(np.searchsorted(times, t)), len(energy) - 1)
        e = float(energy[idx])
        # wedding pacing: longer, softer
        step = 2 if e > 0.65 else 3 if e > 0.4 else 4
        nxt = float(beats[min(i + step, len(beats) - 1)])
        end = min(duration, max(t + 1.1, nxt))
        end = min(duration, max(end, cuts[-1] + 1.0))
        if end - cuts[-1] >= 0.9:
            cuts.append(end)
        i += max(1, step)
    if cuts[-1] < duration:
        cuts.append(duration)

    segs = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        mid = (a + b) / 2
        idx = min(int(np.searchsorted(times, mid)), len(energy) - 1)
        segs.append({"start": a, "end": b, "dur": b - a, "energy": float(energy[idx])})
    return segs


def render_one(video: Path, audio: Path, out: Path, seed: int) -> dict:
    work = WORK / out.stem
    if work.exists():
        for p in work.glob("*"):
            p.unlink()
    work.mkdir(parents=True, exist_ok=True)

    # probe video duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    vdur = float(probe.stdout.strip() or "8")

    segs = soft_segments(audio, max_len=42.0)
    rng = random.Random(seed)
    parts = []
    cursor = 0.4
    for i, seg in enumerate(segs):
        # walk through source with wraps for short stock clips
        if cursor + seg["dur"] > max(1.0, vdur - 0.2):
            cursor = 0.3 + rng.random() * 0.5
        vstart = cursor
        cursor += seg["dur"] * (0.85 + 0.3 * rng.random())

        part = work / f"{i:03d}.mp4"
        # soft romantic grade, 16:9 cinematic
        vf = (
            "scale=1280:720:force_original_aspect_ratio=increase,"
            "crop=1280:720,"
            "eq=contrast=1.08:saturation=1.12:brightness=0.04:gamma=0.98,"
            "unsharp=3:3:0.5:3:3:0.0,"
            "fps=30,format=yuv420p"
        )
        run([
            "ffmpeg", "-y", "-ss", f"{vstart:.3f}", "-i", str(video),
            "-t", f"{seg['dur']:.3f}", "-an", "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(part),
        ])
        parts.append(part)

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = work / "silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])
    run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(audio),
        "-filter_complex", "[1:a]atrim=0:42,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(out),
    ])
    return {
        "output": str(out),
        "video": video.name,
        "audio": audio.name,
        "shots": len(segs),
        "size_kb": out.stat().st_size // 1024,
    }


def main() -> None:
    print("Downloading wedding videos...")
    videos = []
    for vid in VIDEO_IDS:
        dest = VID_DIR / f"wedding_{vid}.mp4"
        url = f"https://assets.mixkit.co/videos/{vid}/{vid}-360.mp4"
        if download(url, dest):
            videos.append(dest)

    print("Downloading romantic music...")
    audios = []
    for mid in MUSIC_IDS:
        dest = AUD_DIR / f"music_{mid}.mp3"
        url = f"https://assets.mixkit.co/music/{mid}/{mid}.mp3"
        if download(url, dest):
            audios.append(dest)

    if len(videos) < 5 or len(audios) < 5:
        raise SystemExit(f"Not enough media: videos={len(videos)} audios={len(audios)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(2026)
    pairs = []
    used_v, used_a = set(), set()
    while len(pairs) < 10:
        v = rng.choice(videos)
        a = rng.choice(audios)
        key = (v.name, a.name)
        if key in pairs:
            continue
        # prefer variety
        if v.name in used_v and len(used_v) < len(videos):
            continue
        pairs.append(key)
        used_v.add(v.name)
        used_a.add(a.name)
        if len(used_v) >= len(videos):
            used_v.clear()

    results = []
    print(f"\nRendering {len(pairs)} wedding tests...")
    for i, (vn, an) in enumerate(pairs, 1):
        video = VID_DIR / vn
        audio = AUD_DIR / an
        out = OUT_DIR / f"test_{i:02d}_{video.stem}_{audio.stem}.mp4"
        print(f"\n[{i}/10] {video.name} + {audio.name}")
        info = render_one(video, audio, out, seed=100 + i)
        info["id"] = i
        results.append(info)
        print(f"  -> {out.name} ({info['size_kb']} KB, {info['shots']} shots)")

    summary = OUT_DIR / "results.json"
    summary.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nDone. Gallery: {OUT_DIR}")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    main()
