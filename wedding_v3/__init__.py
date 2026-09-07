"""Package exports for wedding_v3."""

from __future__ import annotations

__all__ = [
    "MusicAnalysis",
    "analyze_video",
    "top_peaks",
    "build_pool",
    "plan_story",
    "allocate",
    "critique_plan",
    "run_candidates",
]


def __getattr__(name: str):
    if name == "MusicAnalysis":
        from wedding_v3.music import MusicAnalysis

        return MusicAnalysis
    if name in {"analyze_video", "top_peaks"}:
        from wedding_v3 import emotion

        return getattr(emotion, name)
    if name == "build_pool":
        from wedding_v3.shots import build_pool

        return build_pool
    if name == "plan_story":
        from wedding_v3.story import plan_story

        return plan_story
    if name == "allocate":
        from wedding_v3.ranking import allocate

        return allocate
    if name == "critique_plan":
        from wedding_v3.critic import critique_plan

        return critique_plan
    if name == "run_candidates":
        from wedding_v3.pipeline import run_candidates

        return run_candidates
    raise AttributeError(name)
