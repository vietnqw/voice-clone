# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A voice cloning web application powered by OmniVoice — a massively multilingual zero-shot TTS model supporting 600+ languages. The app exposes a FastAPI REST API with a browser UI for managing voice samples and synthesizing speech via voice cloning.

## Installation & Development Setup

Requires Python >=3.10.

```bash
uv sync                          # installs core + resolves PyTorch CUDA automatically
pip install -e ".[webapp]"       # or: uv sync --extra webapp
```

**PyTorch:** `uv sync` automatically installs CUDA 12.8 wheels on Linux/Windows via the pytorch-cuda index in `pyproject.toml`. Pinned to torch==2.8.0 / torchaudio==2.8.0 via `constraint-dependencies`.

No tests or linting are configured.

## Running the App

```bash
docker compose up --build        # recommended — requires 1 NVIDIA GPU
```

Or directly:
```bash
uvicorn webapp.main:app --host 0.0.0.0 --port 8000
```

Env vars: `MODEL_NAME` (default `k2-fsa/OmniVoice`), `DATA_DIR` (default `webapp/data`), `HF_ENDPOINT` (set to `https://hf-mirror.com` if HuggingFace is unreachable).

**Cloudflare Tunnel** (`cloudflare/config.yml`): maps `voice.vietngoquang.com` → `http://tts-app:8000`. Replace `<TUNNEL_UUID>` and provide `cloudflare/credentials.json` (gitignored) before deploying.

## Architecture

```
webapp/
  main.py    — FastAPI app: GET /api/health, /api/samples/* CRUD, synthesis endpoint
  engine.py  — TTSEngine: lazy-load OmniVoice, thread-safe generation, VoiceClonePrompt cache
  store.py   — VoiceStore: persistent voice metadata (voices.json) + audio files (data/audio/)
  static/    — Alpine.js SPA (index.html, app.js, styles.css)

omnivoice/
  models/omnivoice.py   — OmniVoice model; key methods: from_pretrained(), create_voice_clone_prompt(), generate()
  utils/audio.py        — load_audio, remove_silence, trim_long_audio, cross_fade_chunks
  utils/text.py         — chunk_text_punctuation, add_punctuation
  utils/duration.py     — RuleDurationEstimator (language-family-aware)
  utils/lang_map.py     — 600+ language name → ID mappings
  utils/voice_design.py — voice attribute validation (gender, age, pitch, accent, dialect)
  utils/common.py       — get_best_device(), str2bool()
```

**Inference call chain:**
1. `engine.py` calls `OmniVoice.from_pretrained(MODEL_NAME)` at startup
2. Per voice sample: `model.create_voice_clone_prompt(audio_path, ref_text)` → cached `VoiceClonePrompt`
3. Per synthesis: `model.generate(text, language, voice_clone_prompt)` → `np.ndarray` audio at 24 kHz

## Key Design Details

- Audio: 24 kHz, 8 codebooks, HiggsAudioV2 tokenizer (vocab size 1025)
- Long inputs are chunked at 30 s and cross-faded
- Device/dtype auto-detected: CUDA → fp16, CPU → fp32
- Audio tokenizer is moved to CPU after prompt encoding to free VRAM
- Voice data persists in `webapp/data/`: `voices.json` (metadata) + `audio/{uuid}.wav` (files); non-WAV uploads are auto-converted via pydub/ffmpeg
