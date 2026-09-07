"""Creative wedding montage: multi-clip storytelling, no single-clip looping."""

from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parent
VID_DIR = ROOT / "resource" / "video" / "wedding_web"
AUD_DIR = ROOT / "resource" / "audio" / "wedding_web"
OUT_DIR = ROOT / "Output" / "wedding_tests_v2"
WORK = ROOT / "Output" / "wedding_tests_v2_build"

# Story beats for a wedding film (cycle through roles)
ROLES = [
    "detail",   # rings, flowers, hands
    "portrait", # bride / face
    "couple",   # two people together
    "motion",   # walking, dancing, lift
    "wide",     # environment / party
]

# Map known Mixkit IDs to roles (heuristic from filenames/ids)
ROLE_MAP = {
    "wedding_5223.mp4": "detail",   # ring/hands
    "wedding_18204.mp4": "detail",  # bouquet
    "wedding_5213.mp4": "wide",     # decorations
    "wedding_5183.mp4": "detail",   # dress prep
    "wedding_5206.mp4": "couple",   # hand on shoulder
    "wedding_40597.mp4": "portrait",
    "wedding_40591.mp4": "portrait",
    "wedding_40596.mp4": "couple",
    "wedding_40599.mp4": "couple",
    "wedding_40601.mp4": "couple",
    "wedding_36171.mp4": "motion",
    "wedding_4829.mp4": "wide",
}


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "fail")[-2000:])


def probe_dur(path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(p.stdout.strip())
    except Exception:
        return 8.0


def music_plan(audio: Path, max_len: float = 38.0) -> list[dict]:
    y, sr = librosa.load(str(audio), sr=22050, mono=True)
    duration = min(float(librosa.get_duration(y=y, sr=sr)), max_len)
    y = y[: int(duration * sr)]
    tempo, frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beats = librosa.frames_to_time(frames, sr=sr).astype(float)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.frames_to_time(np.arange(len(onset)), sr=sr)
    energy = np.convolve(onset, np.ones(10) / 10, mode="same")
    energy = (energy - energy.min()) / (energy.max() - energy.min() + 1e-8)

    # Build phrase-like cuts: alternate short/long for rhythm
    cuts = [0.0]
    i = 0
    flip = 0
    while i < len(beats) and cuts[-1] < duration - 0.5:
        t = float(beats[i])
        if t <= cuts[-1] + 0.35:
            i += 1
            continue
        idx = min(int(np.searchsorted(times, t)), len(energy) - 1)
        e = float(energy[idx])
        # montage grammar: detail shots shorter, wide longer
        if e > 0.7:
            span = 2
            lo, hi = 0.7, 1.35
        elif flip % 3 == 0:
            span = 4
            lo, hi = 1.6, 2.6
        else:
            span = 3
            lo, hi = 1.1, 1.9
        nxt = float(beats[min(i + span, len(beats) - 1)])
        end = min(duration, max(cuts[-1] + lo, min(nxt, cuts[-1] + hi)))
        cuts.append(end)
        i += max(1, span)
        flip += 1
    if cuts[-1] < duration:
        cuts.append(duration)

    segs = []
    for n, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
        mid = (a + b) / 2
        idx = min(int(np.searchsorted(times, mid)), len(energy) - 1)
        # assign intended role by story arc
        progress = mid / max(duration, 1)
        if progress < 0.15:
            role = "detail"
        elif progress < 0.35:
            role = "portrait"
        elif progress < 0.55:
            role = "couple"
        elif progress < 0.75:
            role = "motion"
        else:
            role = ROLES[n % len(ROLES)]
        segs.append({
            "start": a, "end": b, "dur": b - a,
            "energy": float(energy[idx]), "role": role, "i": n,
        })
    return segs


def classify(videos: list[Path]) -> dict[str, list[Path]]:
    buckets = {r: [] for r in ROLES}
    for v in videos:
        role = ROLE_MAP.get(v.name, "couple")
        buckets[role].append(v)
        # also allow as fallback in adjacent buckets
    # ensure every bucket has something
    all_v = list(videos)
    for r in ROLES:
        if not buckets[r]:
            buckets[r] = all_v[:]
    return buckets


def pick_clip(buckets: dict[str, list[Path]], role: str, used: list[tuple[str, float]], rng: random.Random, need: float) -> tuple[Path, float]:
    """Pick a source clip + unique start time; avoid recent repeats."""
    pool = buckets.get(role) or [p for b in buckets.values() for p in b]
    pool = list(dict.fromkeys(pool))  # unique preserve order
    rng.shuffle(pool)

    recent = {name for name, _ in used[-4:]}
    ranked = sorted(pool, key=lambda p: (p.name in recent, rng.random()))

    for vid in ranked:
        vdur = probe_dur(vid)
        # only use interior that doesn't force loop beyond clip
        if vdur < need + 0.15:
            # clip shorter than shot: take from start, but mark as last-resort
            start = 0.05
        else:
            # pick unused window inside clip
            candidates = []
            step = max(0.4, need * 0.6)
            t = 0.1
            while t + need <= vdur - 0.05:
                key = (vid.name, round(t, 1))
                if all(abs(t - u) > need * 0.8 or n != vid.name for n, u in used):
                    candidates.append(t)
                t += step
            if not candidates:
                start = rng.uniform(0.05, max(0.1, vdur - need))
            else:
                start = rng.choice(candidates)
        used.append((vid.name, float(start)))
        return vid, float(start)

    # fallback
    vid = ranked[0]
    return vid, 0.05


def vf_for(role: str, energy: float) -> str:
    base = (
        "scale=1280:720:force_original_aspect_ratio=increase,"
        "crop=1280:720,"
    )
    if role == "detail":
        # slight push-in feel via crop tighter then scale
        look = "eq=contrast=1.12:saturation=1.18:brightness=0.03:gamma=0.96,unsharp=5:5:0.7:5:5:0.0"
        return base + look + ",fps=30,format=yuv420p"
    if role == "portrait":
        look = "eq=contrast=1.1:saturation=1.15:brightness=0.045:gamma=0.97,unsharp=3:3:0.55:3:3:0.0"
        return base + look + ",fps=30,format=yuv420p"
    if role == "motion" or energy > 0.72:
        look = "eq=contrast=1.14:saturation=1.2:brightness=0.02:gamma=0.95"
        return base + look + ",fps=30,format=yuv420p"
    look = "eq=contrast=1.08:saturation=1.1:brightness=0.04:gamma=0.98"
    return base + look + ",fps=30,format=yuv420p"


def render_montage(videos: list[Path], audio: Path, out: Path, seed: int) -> dict:
    work = WORK / out.stem
    if work.exists():
        for p in work.glob("*"):
            p.unlink()
    work.mkdir(parents=True, exist_ok=True)

    buckets = classify(videos)
    segs = music_plan(audio)
    rng = random.Random(seed)
    used: list[tuple[str, float]] = []
    parts = []
    sources_used = set()

    for seg in segs:
        vid, vstart = pick_clip(buckets, seg["role"], used, rng, seg["dur"])
        sources_used.add(vid.name)
        vdur = probe_dur(vid)
        # clamp so we never request past EOF (no silent freeze loops)
        max_dur = max(0.45, vdur - vstart - 0.05)
        dur = min(seg["dur"], max_dur)
        if dur < 0.45:
            vstart = 0.05
            dur = min(seg["dur"], max(0.45, vdur - 0.1))

        part = work / f"{seg['i']:03d}_{seg['role']}_{vid.stem}.mp4"
        print(f"  shot {seg['i']+1:02d} {seg['role']:<8} {vid.name} @{vstart:.1f}s {dur:.2f}s", flush=True)
        run([
            "ffmpeg", "-y", "-ss", f"{vstart:.3f}", "-i", str(vid),
            "-t", f"{dur:.3f}", "-an", "-vf", vf_for(seg["role"], seg["energy"]),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(part),
        ])
        parts.append(part)

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = work / "silent.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])
    run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(audio),
        "-filter_complex", "[1:a]atrim=0:38,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "17",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(out),
    ])
    return {
        "output": str(out),
        "audio": audio.name,
        "shots": len(parts),
        "unique_clips": sorted(sources_used),
        "clip_count": len(sources_used),
        "size_kb": out.stat().st_size // 1024,
    }


def main() -> None:
    videos = sorted(VID_DIR.glob("wedding_*.mp4"))
    audios = sorted(AUD_DIR.glob("music_*.mp3"))
    if len(videos) < 5 or len(audios) < 3:
        raise SystemExit(f"Need media in {VID_DIR} and {AUD_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(1000)
    results = []
    print(f"Building 10 creative montages from {len(videos)} clips...", flush=True)

    for i in range(1, 11):
        audio = audios[(i - 1) % len(audios)]
        # each film uses ALL clips, shuffled order via seed
        out = OUT_DIR / f"montage_{i:02d}_{audio.stem}.mp4"
        print(f"\n[{i}/10] music={audio.name}", flush=True)
        info = render_montage(videos, audio, out, seed=1000 + i * 17)
        info["id"] = i
        results.append(info)
        print(f"  -> {out.name} | {info['clip_count']} different clips | {info['shots']} shots", flush=True)

    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nDone: {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
