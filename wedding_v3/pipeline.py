"""End-to-end wedding_v3 multi-candidate pipeline."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from wedding_v3.cinematic import render_montage
from wedding_v3.critic import critique_plan, save_critique
from wedding_v3.music import MusicAnalysis
from wedding_v3.ranking import WEIGHT_PROFILES, allocate
from wedding_v3.shots import build_pool, load_pool
from wedding_v3.story import available_roles_from_shots, plan_story
from wedding_v3.titles import TOTAL_TARGET, content_duration

ROOT = Path(__file__).resolve().parents[1]
VID_DIR = ROOT / "resource" / "video" / "wedding_web"
AUD_DIR = ROOT / "resource" / "audio" / "wedding_web"
OUT_DIR = ROOT / "Output" / "wedding_v3"
CACHE = ROOT / "Output" / "v3_cache"


def run_candidates(
    audio: Path,
    shots=None,
    styles: list[str] | None = None,
    profiles: list[str] | None = None,
    render_top: int = 3,
    tag: str = "run",
    out_root: Path | str | None = None,
) -> dict:
    audio = Path(audio)
    if shots is None:
        pool_path = CACHE / "shots" / "pool.json"
        if pool_path.exists():
            shots = load_pool(pool_path)
        else:
            shots = build_pool(VID_DIR)

    roles = available_roles_from_shots(shots)
    analysis = MusicAnalysis(audio)
    analysis.analyze()
    music_out = CACHE / "music" / f"{audio.stem}.json"
    analysis.to_json(music_out)

    styles = styles or ["classic", "emotional", "energetic"]
    profiles = profiles or list(WEIGHT_PROFILES.keys())

    base_out = Path(out_root) if out_root is not None else OUT_DIR
    run_dir = base_out / tag
    plans_dir = run_dir / "plans"
    builds_dir = run_dir / "builds"
    plans_dir.mkdir(parents=True, exist_ok=True)
    builds_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    cid = 0
    # When title cards are gated on, shrink footage so total film stays ~38s.
    story_dur = content_duration(TOTAL_TARGET)
    for style in styles:
        beats = plan_story(analysis, roles, target_duration=story_dur, style=style)
        for profile in profiles:
            cid += 1
            picks = allocate(beats, shots, profile=profile)
            critique = critique_plan(picks, profile=profile)
            name = f"candidate_{cid:02d}_{style}_{profile}"
            plan_path = plans_dir / f"{name}.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "name": name,
                        "style": style,
                        "profile": profile,
                        "audio": str(audio),
                        "critique": critique.to_dict(),
                        "picks": [
                            {
                                "role": p.beat.role,
                                "section": p.beat.section,
                                "dur": p.beat.dur,
                                "slowmo": p.beat.want_slowmo,
                                "xfade": p.beat.want_xfade,
                                "peak": p.beat.is_peak,
                                "score": p.score,
                                "shot_id": p.shot.id,
                                "video": Path(p.shot.video).name,
                                "start": p.shot.start,
                                "best_t": p.shot.best_t,
                                "emotion": p.shot.emotion_score,
                                "reasons": p.reasons,
                            }
                            for p in picks
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            save_critique(critique, plans_dir / f"{name}_critique.json")
            candidates.append(
                {
                    "id": cid,
                    "name": name,
                    "style": style,
                    "profile": profile,
                    "overall": critique.overall,
                    "critique": critique.to_dict(),
                    "picks": picks,
                    "plan_path": str(plan_path),
                }
            )
            print(f"  plan {name}: overall={critique.overall:.2f} shots={len(picks)}", flush=True)

    candidates.sort(key=lambda c: c["overall"], reverse=True)

    # Iterative repair on top candidate: if peak weak, boost peak picks
    best = candidates[0]
    crit = best["critique"]
    if any("weak visual payoff" in p for p in crit.get("problems", [])):
        print("  iterating: reinforcing peak emotion picks", flush=True)
        picks = best["picks"]
        peak_idxs = [i for i, p in enumerate(picks) if p.beat.is_peak]
        smile_shots = sorted(shots, key=lambda s: (s.smile, s.emotion_score), reverse=True)
        used = {p.shot.id for p in picks}
        for i in peak_idxs:
            for s in smile_shots:
                if s.id in used:
                    continue
                if s.faces >= 1 and s.emotion_score >= picks[i].shot.emotion_score:
                    from wedding_v3.ranking import RankedPick

                    picks[i] = RankedPick(beat=picks[i].beat, shot=s, score=picks[i].score + 0.1, reasons=["iter-peak-upgrade"])
                    used.add(s.id)
                    break
        critique2 = critique_plan(picks)
        best["picks"] = picks
        best["critique"] = critique2.to_dict()
        best["overall"] = critique2.overall
        best["name"] = best["name"] + "_iter"
        print(f"  after iter: overall={critique2.overall:.2f}", flush=True)
        candidates.sort(key=lambda c: c["overall"], reverse=True)

    rendered = []
    for c in candidates[:render_top]:
        out = run_dir / f"{c['name']}.mp4"
        work = builds_dir / c["name"]
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        print(f"  rendering {c['name']} (score {c['overall']:.2f})...", flush=True)
        render_montage(c["picks"], audio, out, work, use_xfade=True)
        rendered.append({"name": c["name"], "overall": c["overall"], "path": str(out)})
        print(f"  -> {out}", flush=True)

    summary = {
        "audio": str(audio),
        "n_candidates": len(candidates),
        "leaderboard": [
            {"name": c["name"], "overall": c["overall"], "style": c["style"], "profile": c["profile"]}
            for c in candidates
        ],
        "rendered": rendered,
        "best": rendered[0] if rendered else None,
    }
    (run_dir / "leaderboard.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    print("=== Building shot database ===", flush=True)
    shots = build_pool(VID_DIR, force=False)
    audios = sorted(AUD_DIR.glob("music_*.mp3"))
    # Primary experiment on harp track + one more
    targets = [AUD_DIR / "music_698.mp3", AUD_DIR / "music_428.mp3"]
    targets = [a for a in targets if a.exists()] or audios[:2]

    all_summaries = []
    for audio in targets:
        print(f"\n=== Candidates for {audio.name} ===", flush=True)
        summary = run_candidates(audio, shots=shots, tag=f"sprint_{audio.stem}", render_top=3)
        all_summaries.append(summary)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "sprint_summaries.json").write_text(json.dumps(all_summaries, indent=2), encoding="utf-8")
    print("\nDONE", flush=True)
    for s in all_summaries:
        print(s.get("best"), flush=True)


if __name__ == "__main__":
    main()
