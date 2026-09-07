# Shot database agent (`wedding_v3/shots.py`)

Builds a searchable shot pool from wedding stock clips: time windows with technical quality, emotion scores, role hints, and camera metadata. Results are cached on disk so re-runs skip already-analyzed videos.

## Usage

```bash
# Analyze all clips in the default wedding_web folder and write pool.json
python -m wedding_v3.shots
# or
python wedding_v3/shots.py

# Programmatic
from pathlib import Path
from wedding_v3.shots import analyze_video_shots, build_pool, load_pool

shots = analyze_video_shots(Path("resource/video/wedding_web/wedding_40591.mp4"))
pool = build_pool(Path("resource/video/wedding_web"))
pool = load_pool()  # reads Output/v3_cache/shots/pool.json
```

## Pipeline

1. **Per-video cache lookup** — MD5 key from absolute path + mtime; skip analysis if JSON exists (`force=False`).
2. **Emotion scan** — `analyze_video()` at 2 fps (YuNet faces, smile, sharpness).
3. **Motion probe** — frame-diff heuristic on downscaled grayscale (`static` / `medium` / `high`).
4. **Role hints** — filename stem matched against `ROLE_HINTS` (detail, portrait, couple, motion, wide).
5. **Window split** — ~2.2 s windows, 1.1 s hop; short clips get one window.
6. **Shot assembly** — aggregate moments inside each window; pick best frame for peak/smile.
7. **Pool write** — concatenate all videos into `pool.json`.

## `Shot` fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | str | `{video_stem}_{index:03d}` e.g. `wedding_40591_000` |
| `video` | str | Absolute path to source MP4 (forward slashes) |
| `start` | float | Window start time (seconds) |
| `end` | float | Window end time (seconds) |
| `duration` | float | `end - start` |
| `technical_quality` | float | Mean `FrameMoment.quality` inside window (0–1) |
| `cinematic_quality` | float | Weighted blend of tech, emotion, shot type, motion |
| `emotion_score` | float | Mean emotion score inside window (0–1) |
| `emotional_peak_score` | float | Best moment in window vs global video max (0–1) |
| `subjects` | list[str] | `["person"]` if faces detected, else `["object"]` |
| `faces` | int | Max face count in window |
| `person_ids` | list[str] | Reserved for future identity tracking (usually empty) |
| `semantic_tags` | list[str] | Roles + optional `smile`, `emotional_peak`, `movement` |
| `shot_type` | str | `detail` \| `wide` \| `portrait` \| `couple` (from faces + hints) |
| `camera_motion` | str | `static` \| `medium` \| `high` |
| `composition` | str | `close` (faces) or `detail` (no faces) |
| `story_roles` | list[str] | Deduped role hints + shot type for story planner |
| `music_fit` | float | Placeholder for music–shot affinity (default 0) |
| `novelty` | float | Duplicate-penalty hook for ranking (default 0.5) |
| `best_t` | float | Timestamp of highest-emotion moment in window |
| `smile` | float | Smile score at best moment (0–1) |
| `sharpness` | float | Laplacian sharpness at best moment (0–1) |

### Role hints (`ROLE_HINTS`)

Filename substrings map to editorial roles before face-based typing:

| Role | Example stems |
| --- | --- |
| `detail` | 5223, 18204, 5183, 5218 |
| `portrait` | 40597, 40591 |
| `couple` | 40596, 40599, 40601, 5206 |
| `motion` | 36171 |
| `wide` | 4829, 5213 |

If no hint matches, default role is `couple`.

## Cache layout (`Output/v3_cache/shots/`)

| File | Contents |
| --- | --- |
| `{stem}_{key}.json` | Per-video shot list; `key` = first 16 hex chars of `md5(path + mtime)` |
| `pool.json` | Aggregated shots from `build_pool()` — input to story/ranking/pipeline |

Cache invalidation: delete a per-video JSON or pass `force=True` to `analyze_video_shots` / `build_pool` after the source file changes.

Example per-video cache entry:

```json
{
  "id": "wedding_40591_000",
  "video": "C:/.../wedding_40591.mp4",
  "start": 0.05,
  "end": 2.25,
  "emotion_score": 0.5054,
  "shot_type": "portrait",
  "story_roles": ["portrait"],
  "semantic_tags": ["portrait", "smile", "emotional_peak", "movement"]
}
```

## Integration

- **Story** (`story.py`) — reads `story_roles`, `shot_type`, emotion fields for section-aware beat planning.
- **Ranking** (`ranking.py`) — scores shots by emotion, cinematic quality, novelty, music fit.
- **Pipeline** (`pipeline.py`) — loads `pool.json` if present, otherwise calls `build_pool()`.

## Dependencies

- `opencv-python-headless` — video I/O and motion probe
- `wedding_v3.emotion` — YuNet face/smile analysis (model auto-downloaded to `wedding_v3/models/`)
