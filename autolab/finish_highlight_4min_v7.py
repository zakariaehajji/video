"""Finish interrupted v7 highlight: assemble existing exact parts + mux audio."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wedding_v3.cinematic import (  # noqa: E402
    _assemble_with_selective_xfade,
    _probe_duration,
    run,
)
from wedding_v3.ranking import RankedPick  # noqa: E402
from wedding_v3.shots import Shot  # noqa: E402
from wedding_v3.story import PlannedBeat  # noqa: E402
from wedding_v3 import titles as titles_mod  # noqa: E402
from wedding_v3.titles import bookend_silent  # noqa: E402


def main() -> None:
    run_dir = ROOT / "Output" / "autolab" / "highlight_4min" / "wedding_4min_v7"
    plan_path = run_dir / "plans" / "candidate_01_craft_highlight_4min_A_emotion.json"
    work = run_dir / "builds" / "candidate_01_craft_highlight_4min_A_emotion_iter"
    audio = ROOT / "resource" / "audio" / "wedding_web" / "music_4min_bed.mp3"
    out = run_dir / "candidate_01_craft_highlight_4min_A_emotion_iter.mp4"
    deliver = ROOT / "Output" / "autolab" / "highlight_4min" / "wedding_4min_resume.mp4"

    d = json.loads(plan_path.read_text(encoding="utf-8"))
    picks: list[RankedPick] = []
    t = 0.0
    for x in d["picks"]:
        dur = float(x["dur"])
        beat = PlannedBeat(
            t0=t,
            t1=t + dur,
            dur=dur,
            section=str(x.get("section") or "verse"),
            role=str(x.get("role") or "couple"),
            energy=0.5,
            want_slowmo=bool(x.get("slowmo")),
            want_xfade=bool(x.get("xfade")),
            is_peak=bool(x.get("peak")),
        )
        t += dur
        shot = Shot(
            id=str(x.get("shot_id") or ""),
            video=str(x["video"]),
            start=float(x.get("start") or 0),
            end=float(x.get("start") or 0) + dur,
            duration=max(dur, float(x.get("dur") or 1)),
            emotion_score=float(x.get("emotion") or 0),
            shot_type=str(x.get("role") or "couple"),
            best_t=float(x.get("best_t") or 0),
        )
        picks.append(
            RankedPick(
                beat=beat,
                shot=shot,
                score=float(x.get("score") or 0),
                reasons=list(x.get("reasons") or []),
            )
        )

    parts = sorted(work.glob("*_exact.mp4"))
    if len(parts) != len(picks):
        raise SystemExit(f"exact parts {len(parts)} != picks {len(picks)}")
    print(f"assembling {len(parts)} exact parts...", flush=True)

    planned = float(sum(max(0.35, float(p.beat.dur)) for p in picks))
    titles_mod.TITLE_CARDS = True
    silent = _assemble_with_selective_xfade(picks, parts, work)
    try:
        got = _probe_duration(silent)
    except Exception:
        got = 0.0
    if got + 3.0 < planned:
        print(f"xfade short {got:.1f}<{planned:.1f}; hard concat", flush=True)
        lst = work / "list_hard_finish.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        silent = work / "silent_hard_finish.mp4"
        run(
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
            ]
        )

    if titles_mod.TITLE_CARDS:
        silent = bookend_silent(silent, work / "titles_finish")

    vid_dur = max(1.0, _probe_duration(silent))
    if 0.15 < (planned - vid_dur) <= 2.5:
        padded = work / "silent_endpad_finish.mp4"
        pad = planned - vid_dur
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(silent),
                "-vf",
                f"tpad=stop_mode=clone:stop_duration={pad:.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "17",
                "-an",
                str(padded),
            ]
        )
        silent = padded
        vid_dur = planned

    print(f"mux audio to {vid_dur:.2f}s...", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent),
            "-i",
            str(audio),
            "-filter_complex",
            f"[1:a]atrim=0:{vid_dur:.3f},asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "17",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    shutil.copy2(out, deliver)
    print(f"best duration={_probe_duration(out):.2f}s -> {deliver}", flush=True)


if __name__ == "__main__":
    main()
