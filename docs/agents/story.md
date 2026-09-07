# Agent: Story

Adaptive planner in `wedding_v3/story.py`.

- Maps music sections (intro/build/verse/chorus/peak/outro) → preferred shot roles
- Skips roles with no footage
- Styles: classic / emotional / energetic change base shot duration
- Peak sections request shorter shots + slow-mo flags for couple/portrait
- Soft sections request fade-in flags

Not a fixed recipe: section labels come from music analysis; available roles come from shot DB.
