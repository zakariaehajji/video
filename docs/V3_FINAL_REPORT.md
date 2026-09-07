# V3 Final Report

## Scores

```text
V2 BASELINE (human rubric): 6.4/10
V3 FINAL (auto-critic, measurable): 8.15/10
V3 FINAL (same human rubric as V2, fair compare): 7.6/10
Improvement (fair): +1.2
```

### Table (fair human re-rate vs V2)

| Criterion    |  V2 | V3 |
| ------------ | --: | -: |
| Creativity   | 5.5 | 7.0 |
| Montage      | 7.0 | 7.8 |
| Story        | 6.5 | 7.6 |
| Music Sync   | 6.0 | 7.2 |
| Wedding Feel | 7.0 | 8.0 |
| Polish       | 5.0 | 6.5 |
| Emotion      | 4.0 | 6.5 |
| Overall      | 6.4 | 7.6 |

### Auto-critic best candidate (`emotional` + `A_emotion` on music_428)

| Metric | Score |
|--------|------:|
| visual_quality | 6.37 |
| story_coherence | 10.0 |
| emotion | 7.10 |
| music_sync | 7.91 |
| wedding_feeling | 9.0 |
| variety | 9.09 |
| continuity | 10.0 |
| pacing | 6.5 |
| technical_quality | 7.44 |
| polish | 6.5 |
| **overall** | **8.15** |

Problems still flagged: pacing can still feel busy.

---

## Best improvements

1. **Shot database (138 shots)** with YuNet faces, smile/emotion, sharpness, quality, roles — cached in `Output/v3_cache/shots/`
2. **Music intelligence** — BPM, beats, sections (intro/build/chorus/peak/outro), energy peaks
3. **Multi-candidate search** — 12+ plans × weight profiles; pick winner by critic (not first render)
4. **Peak-aware selection** — prefer smile/face shots on musical peaks; iterative peak upgrade
5. **Context slow-mo / fade-in** — only when section + emotion justify it

## Worst failures / limits

- Still stock Mixkit clips (no real ceremony vows/kiss guaranteed)
- Emotion is heuristic smile geometry, not a trained FER model
- Torch is CPU-only; GTX 1650 unused
- Pacing still rated mid by critic (many cuts)
- No true identity tracking (bride vs random woman) beyond face counts
- No lyric-aware cuts

## Experiments

| ID | What | Best overall |
|----|------|-------------:|
| sprint_music_698 | 3 styles × 4 weights, 12 candidates | 7.84 |
| sprint_music_428 | same | 8.03 |
| sprint_music_428_v3b | longer pacing + emotion-heavy | **8.15** |

Winning recipe: `style=emotional`, `profile=A_emotion`, music_428.

## Models / deps

- OpenCV YuNet ONNX face detector
- Optional MediaPipe (installed, not required)
- librosa beat/onset/chroma novelty
- FFmpeg libx264 + loudnorm
- No paid LLM APIs used in V3 offline path

## Processing

- Shot pool build: ~12 videos → 138 shots (~55s)
- Candidate planning: seconds
- Render top-2: ~2 min each run
- Cache avoids re-analysis

## Candidates generated

- music_698: 12 plans, 3 rendered
- music_428: 12 plans, 3 rendered
- music_428_v3b: 6 plans, 2 rendered
- **Best file:** `Output/wedding_v3/BEST_v3.mp4`

## Remaining weaknesses

1. Choppy pacing vs luxury wedding films
2. Weak FER / no kiss-hug classifiers
3. No crossfade graph (only fade-in)
4. No titles (names/date)
5. 360p/720p stock ceiling

## Recommended V4

1. Train/use a lightweight smile/kiss classifier on faces
2. Phrase-level edit (8-bar blocks) with fewer cuts
3. True xfade between soft section boundaries
4. Opening/ending cards with couple names
5. CUDA torch build to speed analysis
6. Wire `wedding_v3` “Create film” button in Streamlit for one-click offline renders
