# video-use integration (browser-use)

Repo: https://github.com/browser-use/video-use  
Local clone: `~/Developer/video-use` (junctioned into Cursor/Claude skills as `video-use`)

## How it fits the wedding lab

| Layer | Role |
|-------|------|
| **wedding_v3** (ours) | Shot pool, wedding gate, day-story ranking, music-driven 4min montage |
| **video-use** | Transcript/EDL editor for speech-heavy footage; `timeline_view` self-eval; grade presets |

**Do not replace** wedding_v3 with video-use for silent Mixkit stock + music beds. video-use is **audio-primary** (word cuts via ElevenLabs Scribe). Our highlight films are **visual-primary**.

## Use now (no API key)

```bash
python autolab/video_use_bridge.py timeline Output/autolab/highlight_4min/wedding_4min_resume.mp4
python autolab/video_use_bridge.py grade-analyze Output/autolab/highlight_4min/wedding_4min_resume.mp4
```

PNGs land in `Output/autolab/highlight_4min/edit/verify/`.

## Use later (needs ElevenLabs)

1. Paste `ELEVENLABS_API_KEY` into `~/Developer/video-use/.env`
2. Drop real ceremony/speech takes in a folder
3. Ask the agent: *inventory these takes and propose a wedding-film strategy*
4. After confirm → EDL → render → self-eval via `timeline_view`

## Borrowed craft into wedding_v3 (next experiments)

- 30ms `afade` at every picture cut (video-use hard rule)
- Optional `warm_cinematic` grade pass on final deliverable
- Cut-boundary filmstrip self-eval before claiming a score
