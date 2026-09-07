"""Smoke tests for wedding_v3 music and optional shot pool cache."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

AUDIO = ROOT / "resource" / "audio" / "wedding_web" / "music_698.mp3"
POOL = ROOT / "Output" / "v3_cache" / "shots" / "pool.json"


def test_music_analysis_bpm_and_sections():
    from wedding_v3.music import MusicAnalysis

    assert AUDIO.exists(), f"missing fixture: {AUDIO}"
    analysis = MusicAnalysis(AUDIO)
    result = analysis.analyze()
    assert result["bpm"] > 0
    assert result["sections"]


skip_no_pool = pytest.mark.skipif(not POOL.exists(), reason="pool.json not built yet") if pytest else lambda f: f


@skip_no_pool
def test_shot_pool_loads_when_cached():
    from wedding_v3.shots import load_pool

    shots = load_pool(POOL)
    assert len(shots) > 0


if __name__ == "__main__":
    test_music_analysis_bpm_and_sections()
    if POOL.exists():
        test_shot_pool_loads_when_cached()
        print("pool.json: OK")
    else:
        print("pool.json: skipped (not present)")
    print("smoke: OK")
