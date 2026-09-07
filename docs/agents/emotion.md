# Emotion module (`wedding_v3/emotion.py`)

Local, API-free analysis for picking emotionally strong wedding clips.

## What it returns

Each sampled frame becomes a `FrameMoment`:

| Field | Range | Meaning |
|-------|-------|---------|
| `t` | seconds | Timestamp in source video |
| `emotion_score` | 0–1 | Combined ranking score (smile + faces + quality) |
| `smile` | 0–1 | Estimated smile intensity |
| `face_count` | int | Faces detected in frame |
| `sharpness` | 0–1 | Laplacian blur proxy |
| `quality` | 0–1 | Sharpness + exposure composite |

Use `top_peaks()` to get non-overlapping emotional highlights for montage in/out points.

## Quick start

```python
from pathlib import Path
from wedding_v3.emotion import analyze_video, top_peaks

video = Path("resource/video/wedding_web/wedding_40597.mp4")
moments = analyze_video(video, sample_fps=2.0)
peaks = top_peaks(moments, n=10, min_gap=0.75)

for p in peaks:
    print(p.t, p.emotion_score, p.smile, p.face_count)
```

CLI smoke test:

```bash
.venv\Scripts\python.exe -m wedding_v3.emotion
.venv\Scripts\python.exe -m wedding_v3.emotion resource\video\wedding_web\wedding_5206.mp4
.venv\Scripts\python.exe -m wedding_v3.emotion --mediapipe   # optional refinement
```

## Pipeline

1. **Face detection** — OpenCV YuNet (`FaceDetectorYN`) with ONNX model auto-downloaded to `wedding_v3/models/`.
2. **Smile estimate** — YuNet mouth-corner landmarks + lower-face edge/aspect heuristics.
3. **Optional refine** — MediaPipe Face Landmarker (`--mediapipe` or `use_mediapipe=True`) blends geometry-based smile cues.
4. **Quality** — Full-frame Laplacian sharpness and exposure/clipping penalty.
5. **Emotion score** — Weighted blend: 40% smile, 20% face presence, 25% quality, 15% multi-face bonus (couple shots).

## Tuning

| Parameter | Default | Notes |
|-----------|---------|-------|
| `sample_fps` | 2.0 | Lower = faster scan; 2–4 good for short stock clips |
| `resize_width` | 960 | Downscale for speed; faces still detected at 720p sources |
| `conf_threshold` | 0.55 | YuNet face confidence |
| `min_gap` | 0.75 s | Peak suppression in `top_peaks` |
| `max_seconds` | None | Cap analysis for long files |

## Integration idea (montage v3)

Replace static `ROLE_MAP` heuristics with per-clip peak mining:

```python
moments = analyze_video(clip_path, sample_fps=3.0)
peaks = top_peaks(moments, n=5)
# Use peak timestamps as candidate vstart for portrait/couple roles
```

Prefer peaks with `face_count >= 1`, `quality >= 0.45`, and `smile >= 0.35` for highlight beats; use low-face high-quality peaks for detail/wide B-roll.

## Models on disk

| File | Size | Source |
|------|------|--------|
| `wedding_v3/models/face_detection_yunet_2026may.onnx` | ~230 KB | [OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) |
| `wedding_v3/models/face_landmarker.task` | ~3 MB | Google MediaPipe (only if `--mediapipe`) |

First run downloads missing models; no API keys.

## Dependencies

- **Required:** `opencv-python-headless` (already in project requirements)
- **Optional:** `mediapipe` (installed in venv during this work; refines smile on close-ups)
