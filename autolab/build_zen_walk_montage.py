"""Build a zen travel highlight montage from a long silent walking video.

Samples frames across the source, scores visual interest (sharpness,
color pop, blue-city bias, motion proxy), picks non-overlapping clips,
writes a video-use EDL + ffmpeg concat render with music.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "Output" / "autolab" / "videoplayback_montage"
SRC = WORK / "source.mp4"
EDIT = WORK / "edit"
VERIFY = EDIT / "verify"


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def grab_frame(t: float, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(SRC),
            "-frames:v",
            "1",
            "-q:v",
            "4",
            str(dest),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return r.returncode == 0 and dest.exists() and dest.stat().st_size > 2000


def score_frame(path: Path) -> dict:
    im = Image.open(path).convert("RGB").resize((320, 180))
    arr = np.asarray(im).astype(np.float32)
    gray = arr.mean(axis=2)
    # Laplacian-ish sharpness
    gy, gx = np.gradient(gray)
    sharp = float(np.mean(gx * gx + gy * gy))
    # saturation / colorfulness
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = float(np.mean((mx - mn) / (mx + 1e-3)))
    # Chefchaouen blue bias (B channel dominance in mid tones)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    blue = float(np.mean((b > r + 15) & (b > g + 5)))
    # avoid near-black / near-white / heavy text overlays (top/bottom bright bands)
    mean_l = float(gray.mean())
    exposure = 1.0 - abs(mean_l - 120) / 120
    # watermark-ish: very bright text band bottom-left often "QUICK PREVIEW"
    bottom = gray[-24:, :80]
    watermark_pen = 0.15 if float(bottom.mean()) > 180 else 0.0
    score = 0.35 * min(sharp / 80.0, 1.5) + 0.25 * sat + 0.25 * blue + 0.2 * max(exposure, 0)
    score -= watermark_pen
    return {
        "score": round(score, 4),
        "sharp": round(sharp, 2),
        "sat": round(sat, 3),
        "blue": round(blue, 3),
        "mean_l": round(mean_l, 1),
    }


def pick_clips(
    candidates: list[dict],
    target_dur: float = 150.0,
    clip_dur: float = 3.2,
    min_gap: float = 8.0,
    source_dur: float | None = None,
) -> list[dict]:
    # diversify by time buckets (story spine across the walk)
    duration = float(source_dur or 0.0)
    if duration <= 0 and candidates:
        duration = max(c["t"] for c in candidates)
    buckets = 10
    need = int(math.ceil(target_dur / clip_dur)) + 2
    per_bucket = max(2, int(math.ceil(need / buckets)) + 1)
    chosen: list[dict] = []
    used_t: list[float] = []

    def ok(t: float) -> bool:
        return all(abs(t - u) >= min_gap for u in used_t)

    for bi in range(buckets):
        t0 = duration * bi / buckets
        t1 = duration * (bi + 1) / buckets
        pool = [c for c in candidates if t0 <= c["t"] < t1]
        pool.sort(key=lambda c: c["score"], reverse=True)
        n = 0
        for c in pool:
            if n >= per_bucket:
                break
            if not ok(c["t"]):
                continue
            # skip very weak frames
            if c["score"] < 0.45:
                continue
            start = max(0.0, c["t"] - 0.35)
            end = min(duration - 0.05, start + clip_dur)
            if end - start < 2.0:
                continue
            chosen.append({**c, "start": round(start, 3), "end": round(end, 3)})
            used_t.append(c["t"])
            n += 1

    # fill remaining from global top if short
    if sum(c["end"] - c["start"] for c in chosen) < target_dur * 0.85:
        for c in sorted(candidates, key=lambda x: x["score"], reverse=True):
            if not ok(c["t"]) or c["score"] < 0.5:
                continue
            start = max(0.0, c["t"] - 0.35)
            end = min(duration - 0.05, start + clip_dur)
            chosen.append({**c, "start": round(start, 3), "end": round(end, 3)})
            used_t.append(c["t"])
            if sum(x["end"] - x["start"] for x in chosen) >= target_dur:
                break

    chosen.sort(key=lambda c: c["start"])
    total = 0.0
    out = []
    for c in chosen:
        if total >= target_dur:
            break
        out.append(c)
        total += c["end"] - c["start"]
    return out


def write_edl(clips: list[dict], music: Path | None) -> Path:
    ranges = []
    for i, c in enumerate(clips):
        ranges.append(
            {
                "source": "walk",
                "start": c["start"],
                "end": c["end"],
                "beat": f"B{i:02d}",
                "quote": "",
                "reason": f"score={c['score']} blue={c['blue']} sharp={c['sharp']}",
            }
        )
    total = sum(r["end"] - r["start"] for r in ranges)
    edl = {
        "version": 1,
        "sources": {"walk": str(SRC.resolve()).replace("\\", "/")},
        "ranges": ranges,
        "grade": "warm_cinematic",
        "overlays": [],
        "total_duration_s": round(total, 3),
        "music": str(music.resolve()).replace("\\", "/") if music else "",
    }
    path = EDIT / "edl.json"
    path.write_text(json.dumps(edl, indent=2), encoding="utf-8")
    return path


def render_ffmpeg(clips: list[dict], music: Path, out: Path, target: float = 150.0) -> None:
    """Reliable silent-source montage: extract → concat → music + grade."""
    clips_dir = EDIT / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, c in enumerate(clips):
        part = clips_dir / f"part_{i:03d}.mp4"
        # scale 1080p, warm grade, 30fps for smooth walk feel
        vf = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
            "eq=contrast=1.10:brightness=-0.02:saturation=0.92,"
            "colorbalance=rs=0.02:bs=-0.03:rm=0.04:bm=-0.02:rh=0.06:bh=-0.04,"
            "fps=30,format=yuv420p"
        )
        dur = c["end"] - c["start"]
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{c['start']:.3f}",
            "-i",
            str(SRC),
            "-t",
            f"{dur:.3f}",
            "-an",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(part),
        ]
        print(f"  extract {i+1}/{len(clips)} @{c['start']:.1f}s", flush=True)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        parts.append(part)

    lst = EDIT / "concat.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    silent = EDIT / "picture.mp4"
    subprocess.run(
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
            str(silent),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # soft crossfade-ish: just music under picture, fade in/out audio
    pic_dur = probe_duration(silent)
    use = min(pic_dur, target, probe_duration(music))
    # short xfades via xfade chain would be heavy; use music fades instead
    af = f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(0, use-2.5):.3f}:d=2.5,volume=0.85"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(silent),
        "-stream_loop",
        "-1",
        "-i",
        str(music),
        "-t",
        f"{use:.3f}",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-af",
        af,
        "-shortest",
        "-movflags",
        "+faststart",
        str(out),
    ]
    print("  mux music → final", flush=True)
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    EDIT.mkdir(parents=True, exist_ok=True)
    VERIFY.mkdir(parents=True, exist_ok=True)
    dur = probe_duration(SRC)
    print(f"source duration={dur:.1f}s", flush=True)

    step = 5.0
    candidates = []
    t = 5.0
    while t < dur - 4:
        frame = VERIFY / f"score_{int(t):05d}.jpg"
        if not frame.exists():
            if not grab_frame(t, frame):
                t += step
                continue
        try:
            s = score_frame(frame)
        except Exception:
            t += step
            continue
        candidates.append({"t": round(t, 2), **s})
        if int(t) % 60 == 0:
            print(f"  scored @{t:.0f}s n={len(candidates)}", flush=True)
        t += step

    # persist full candidate list for reruns
    (EDIT / "candidates_all.json").write_text(
        json.dumps(candidates, indent=2), encoding="utf-8"
    )
    by_score = sorted(candidates, key=lambda c: c["score"], reverse=True)
    (EDIT / "candidates_top.json").write_text(
        json.dumps(by_score[:80], indent=2), encoding="utf-8"
    )
    print(
        f"candidates={len(candidates)} top={by_score[0] if by_score else None}",
        flush=True,
    )

    clips = pick_clips(
        candidates,
        target_dur=150.0,
        clip_dur=3.6,
        min_gap=12.0,
        source_dur=dur,
    )
    print(f"picked {len(clips)} clips ~{sum(c['end']-c['start'] for c in clips):.1f}s", flush=True)
    (EDIT / "picked.json").write_text(json.dumps(clips, indent=2), encoding="utf-8")

    music_candidates = [
        EDIT / "music_zen.mp3",
        ROOT / "resource" / "audio" / "wedding_web" / "music_4min_bed.mp3",
        ROOT / "resource" / "audio" / "wedding_web" / "music_139.mp3",
        ROOT / "resource" / "audio" / "babydoll.mp3",
    ]
    music = next((p for p in music_candidates if p.exists() and p.stat().st_size > 100_000), None)
    if not music:
        raise SystemExit("no music bed found")
    print(f"music={music}", flush=True)

    write_edl(clips, music)
    out = EDIT / "final.mp4"
    render_ffmpeg(clips, music, out, target=150.0)
    print(f"done → {out} ({probe_duration(out):.2f}s)", flush=True)


if __name__ == "__main__":
    main()
