# Emotion selection research (wedding montage v3)

Goal: improve wedding highlight **emotion-aware clip selection** on Windows, Python 3.12, CPU-only torch, GTX 1650 unused, **no paid APIs**.

## Constraints

| Constraint | Implication |
|------------|-------------|
| No cloud vision APIs | Must run fully local |
| CPU-only / 4 GB GPU | Avoid heavy deep emotion classifiers on GPU; keep inference lightweight |
| Short Mixkit wedding clips (~5–15 s) | Frame sampling at 2–4 fps is enough |
| Existing stack: OpenCV, librosa, ffmpeg | Prefer OpenCV-first; reuse video I/O patterns from `batch_wedding_montage_v2.py` |

## Options evaluated

### 1. OpenCV Haar cascades (rejected as primary)

- **Pros:** Zero download if bundled, fast on CPU.
- **Cons:** OpenCV **5.0** in this venv ships an empty `cv2.data.haarcascades` directory (no XML files). Would require manual fetch of `haarcascade_frontalface_default.xml` and `haarcascade_smile.xml`.
- **Verdict:** Fallback only; not reliable out of the box here.

### 2. OpenCV YuNet / `FaceDetectorYN` (chosen — primary)

- **Pros:** Small ONNX (~230 KB), fast, returns **5 facial landmarks** (eyes, nose, mouth corners) usable for smile geometry; works with OpenCV 5.x dynamic ONNX (`face_detection_yunet_2026may.onnx`).
- **Cons:** First-run model download; smile is inferred heuristically, not a trained emotion classifier.
- **Verdict:** Best balance of accuracy, size, and zero API cost.

### 3. OpenCV DNN SSD Caffe (rejected)

- **Pros:** Well-known `res10_300x300_ssd` model.
- **Cons:** OpenCV 5 removed `readNetFromCaffe`; Caffe weights add friction vs YuNet ONNX.

### 4. MediaPipe Face Landmarker (optional add-on)

- **Pros:** Stable lip/cheek landmarks; improves smile on close-ups when model is present.
- **Cons:** Extra ~3 MB model download; `mediapipe` 1.x uses Tasks API (different from legacy `solutions` API).
- **Verdict:** Installed successfully; enabled via `use_mediapipe=True` / `--mediapipe`, blended 45% with YuNet heuristics.

### 5. DeepFace / FER+ / torchvision emotion nets (rejected)

- **Pros:** Trained emotion labels.
- **Cons:** Heavy deps, slow cold start on CPU, overlap with unused torch GPU path; overkill for ranking B-roll peaks.

### 6. LLM / paid vision APIs (rejected)

- Violates project goal; adds latency and cost per clip.

## Chosen architecture

```
video → sample frames (2 fps, max width 960)
      → YuNet faces + landmarks
      → smile heuristic (mouth width, corner lift, ROI edges)
      → [optional] MediaPipe landmark blend
      → sharpness (Laplacian) + exposure penalty
      → emotion_score = f(smile, face_count, quality)
      → top_peaks() with temporal NMS
```

## Smile heuristic rationale

Wedding montages prioritize **visible joy** and **couple presence**, not fine-grained FER labels.

Signals used:

1. **Mouth width / face width** — smiles widen the mouth.
2. **Corner lift** — mouth corners move upward relative to mouth center (image coordinates).
3. **Nose-to-mouth vertical spacing** — slight opening consistent with natural smiles.
4. **Lower-face edge density** — backup when landmarks are noisy on profile/partial faces.

`emotion_score` intentionally boosts multi-face frames (bride + groom) while still requiring minimum quality so blurry dark frames do not rank high.

## Quality metrics

| Metric | Method | Why |
|--------|--------|-----|
| Sharpness | Laplacian variance on 320×180 grayscale | Cheap, correlates with usable cuts |
| Exposure | Mean luminance vs ~120 + clipping ratio | Penalizes crushed shadows and blown highlights |
| Quality | 0.62·sharp + 0.38·exposure | Favor sharp, well-exposed emotional beats |

## Expected limitations

- Profile/back-of-head shots score low on smile (by design).
- Group dance wide shots may get multi-face bonus without strong smile — filter with `smile` threshold for portrait beats.
- Heuristic smile ≠ ground-truth FER; validate peaks visually before auto-cutting.

## Next steps (not implemented here)

- Wire `top_peaks()` into a `batch_wedding_montage_v3.py` role picker.
- Cache per-clip JSON profiles under `Output/wedding_v3/emotion/` to avoid re-scanning.
- A/B montages: static `ROLE_MAP` vs emotion-driven `vstart` selection.

## Install notes (this session)

| Package | Result |
|---------|--------|
| `opencv-python-headless` | Already present (5.0.0) |
| `mediapipe` | **Installed** (1.0.1) — optional |
| YuNet ONNX | **Downloaded** to `wedding_v3/models/` |
| Haar cascades | Not bundled in OpenCV 5 — skipped |

No install failures for required components.
