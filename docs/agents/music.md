# Music analysis agent (`wedding_v3.music`)

Librosa-only music analysis for wedding montage v3. Produces beat-aligned timing cues, section labels, and energy peaks for cut planning.

## Usage

```bash
python -m wedding_v3.music resource/audio/wedding_web/music_698.mp3 \
  --out Output/v3_cache/music_test.json
```

Programmatic:

```python
from wedding_v3 import MusicAnalysis

analysis = MusicAnalysis("resource/audio/wedding_web/music_698.mp3")
data = analysis.analyze()
analysis.to_json("Output/v3_cache/music_test.json")
```

## Output schema

| Field | Description |
| --- | --- |
| `source` | Absolute path to the input audio |
| `duration` | Track length in seconds |
| `sr` | Analysis sample rate (default 22050) |
| `bpm` | Estimated tempo |
| `beat_times` | Beat onset timestamps (seconds) |
| `downbeat_times` | Every 4th beat (approximate bar starts) |
| `energy_curve` | Normalized onset-energy curve `{times, values}` |
| `sections` | Segments with `start`, `end`, `mean_energy`, `label` |
| `phrases` | ~8-beat groupings with `start`, `end`, beat indices |
| `peaks` | Top local energy peaks `{time, energy}` |

### Section labels

Heuristic labels from energy and position:

- **intro** — first section, below-median energy
- **build** — rising energy in the first half
- **chorus** — high energy (≥70th percentile), not the global peak
- **peak** — highest mean-energy section
- **outro** — final section
- **verse** — default fallback

Segmentation combines chroma + energy novelty peaks, snapped to roughly equal spans (minimum ~5 s per section). Labels are practical hints, not ground-truth song structure.

## Dependencies

- `librosa` (loaded via project venv; not pinned in `requirements.txt` but used elsewhere in the repo)
- `numpy`

## Integration notes

- Downbeats are approximate (every 4 beats); fine for montage pacing, not for score-accurate sync.
- Peak times align with smoothed onset strength — good punch-cut anchors.
- Phrase boundaries follow beat groups; pair with `downbeat_times` for bar-aligned edits when needed.
