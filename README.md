# AVEngine

Automated faceless short-video pipeline: script spec -> ElevenLabs voice -> real stock footage (Pixabay, optional NASA/Pexels) with AI-image fallback (SDXL-Lightning on an on-demand RunPod pod) -> Ken Burns clips -> kinetic captions -> 1080x1920 MP4, plus a contact sheet and license log per render.

## Layout
- `viral_custom.py` - main pipeline (`--spec`, `--dry-run`, `--lang`, `--stock-sources`, `--backend`).
- `stock_footage.py`, `topic_check.py` - footage providers and the free footage preflight.
- `script_gen.py` - private script drafter using a local Ollama model (`ollama/scriptwriter.Modelfile`). Drafts are local-only and never published.
- `runpod_images.py`, `runpod_flux_server.py`, `ai_video_engine.py` - GPU pod lifecycle and key store.
- `viral_recreation_caesar.py` - renderer helpers (captions, scene clips).
- `open-webui/video_studio.py` - Open WebUI tool: draft, check footage, render with an on-screen spend confirmation.
- `specs/` - vetted example specs. `faceless_studio.py` and `open-webui/faceless_video.py` are the older flow.

## Setup
1. Python 3 with `requests`, `Pillow`, `runpod`; `ffmpeg` on PATH or in `~/bin`.
2. Keys are stored outside the repo in `~/.ai_video_keys.json` (mode 600): `elevenlabs`, `pixabay`, `runpod_api_key`. Set them with `python3 ai_video_engine.py --set-key <service> <value>`.
3. Preflight, then render: `python3 topic_check.py specs/<spec>.json` then `python3 viral_custom.py --spec specs/<spec>.json --stock-sources pixabay`.

## Rules the pipeline follows
- Review the contact sheet after every render: a tag match is not a relevance match.
- Scenes without real footage must be marked `"ai": true`, and AI content must be labelled when published.
- Pods are terminated after each run; check Pixabay terms (24h search caching, no bulk scraping).
- `drafts/` and `local_only/` are git-ignored on purpose.
