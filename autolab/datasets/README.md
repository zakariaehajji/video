# Legal wedding stock dataset

Downloads **only** free commercial stock (Mixkit / Pexels / Pixabay).
Never scrape paid templates, YouTube films, or course videos.

## Setup

```powershell
# Optional (greatly increases volume):
# https://www.pexels.com/api/
# https://pixabay.com/api/docs/
```

Add to `autolab/.env` (gitignored):

```env
PEXELS_API_KEY=
PIXABAY_API_KEY=
```

Mixkit works **without** a key.

## Run

```powershell
# Mixkit only (no key) — resume-safe
.\.venv\Scripts\python.exe -m autolab.datasets.download_stock --sources mixkit --target 1000

# All sources when keys are set
.\.venv\Scripts\python.exe -m autolab.datasets.download_stock --sources mixkit,pexels,pixabay --target 1000
```

Clips land in:

```text
resource/video/library/mixkit/
resource/video/library/pexels/
resource/video/library/pixabay/
```

Manifest: `autolab/datasets/manifest.json`

## Rebuild shot pool after download

```powershell
.\.venv\Scripts\python.exe -m wedding_v3.shots
```
