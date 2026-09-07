# Performance notes (wedding_v3)

Practical guidance for running the offline montage pipeline on typical dev hardware (Windows, GTX 1650, CPU-only PyTorch).

## Cache aggressively

Repeated work is the main cost. Persist analysis to disk and reuse it:

| Cache path | Written by | Contents |
| --- | --- | --- |
| `Output/v3_cache/shots/{stem}_{hash}.json` | `analyze_video_shots()` | Per-video shot windows |
| `Output/v3_cache/shots/pool.json` | `build_pool()` | Full shot database |
| `Output/v3_cache/music/{stem}.json` | `pipeline.run_candidates()` | MusicAnalysis JSON |

- Shot cache keys include file mtime — editing a clip invalidates only that video's JSON.
- Pipeline loads `pool.json` when present; skip `build_pool()` during iteration on story/rank/render.
- Music JSON is cheap to regenerate but saving it avoids re-running librosa on every candidate sweep.

## PyTorch runs on CPU only

The project venv ships a **CPU-only** `torch` build. Wedding v3 emotion and shot analysis do **not** use torch at all — they rely on OpenCV and NumPy.

A GTX 1650 (4 GB) is present on the target machine but **unused** by the current torch install and by `wedding_v3/*`. Legacy `src/` ASR/diarization paths may attempt CUDA when a GPU build is installed; that is separate from v3.

Do not expect GPU speedups for v3 without changing dependencies and code paths.

## OpenCV YuNet is lightweight

Face detection in `wedding_v3/emotion.py` uses the YuNet ONNX model (~230 KB):

- Auto-downloaded once to `wedding_v3/models/face_detection_yunet_2026may.onnx`
- Runs on CPU via `cv2.FaceDetectorYN`
- Default `sample_fps=2.0` keeps per-clip analysis to a few seconds for short stock footage

Optional MediaPipe landmarker adds ~3 MB and extra CPU time; use only when refining smile on close-ups.

## Other bottlenecks

| Stage | Typical cost | Mitigation |
| --- | --- | --- |
| Shot pool build | Linear in clip count × duration | Cache per-video JSON; lower `sample_fps` in emotion if needed |
| Music analysis | Seconds per track | Cache JSON under `Output/v3_cache/music/` |
| FFmpeg render | Dominates pipeline wall time | Reduce `render_top` in pipeline; iterate on plans without re-rendering |
| Motion probe | Small vs emotion scan | Fixed 2 fps sample on 160×90 grayscale |

## Recommended workflow

1. Run `python -m wedding_v3.shots` once (or until pool is complete) — leave `pool.json` in place.
2. Tune story/ranking/critic with cached pool + cached music JSON.
3. Render only top candidates when scores stabilize.

See [testing.md](testing.md) for commands and [video.md](video.md) for cache file layout.
