# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

OmniVoice is a massively multilingual zero-shot TTS (text-to-speech) model supporting 600+ languages. It uses a diffusion language model-style architecture built on top of a transformer LLM (default: Qwen3-0.6B) and encodes/decodes audio via a multi-codebook tokenizer (HiggsAudioV2). Three generation modes are supported: voice cloning, voice design (attribute-based), and auto voice.

## Installation & Development Setup

Requires Python >=3.10.

**Development install (editable):**
```bash
pip install -e .
# or with uv (recommended):
uv sync
```

**With extras:**
```bash
pip install -e ".[eval]"       # WER, speaker similarity, MOS metrics
pip install -e ".[training]"   # accelerate, gradio, tensorboardX, webdataset
# webapp extras (fastapi, uvicorn) are declared in pyproject.toml but installed via Docker
uv sync --extra eval           # uv equivalent
```

**PyTorch:** Must be installed separately before `omnivoice`. Use CUDA 12.8 wheels for NVIDIA GPUs (`https://download.pytorch.org/whl/cu128`). `uv sync` handles this automatically via `pyproject.toml` index configuration.

**No tests or linting** are configured in this project. Validation is done via the example scripts in `examples/`.

## CLI Entry Points

| Command | Source | Purpose |
|---|---|---|
| `omnivoice-infer` | `omnivoice/cli/infer.py` | Single-item inference |
| `omnivoice-infer-batch` | `omnivoice/cli/infer_batch.py` | Multi-GPU batch inference |
| `omnivoice-demo` | `omnivoice/cli/demo.py` | Gradio web UI |

**Key inference flags** (`omnivoice-infer`):
- `--text`, `--output` (required)
- `--ref_audio`, `--ref_text` for voice cloning; `--instruct` for voice design
- `--num_step 32`, `--guidance_scale 2.0`, `--speed 1.0`, `--t_shift 0.1`
- `--denoise True`, `--postprocess_output True`

**Batch inference test list** (JSONL, one item per line):
```jsonl
{"id": "sample_001", "text": "Hello", "ref_audio": "path.wav", "ref_text": "transcript", "language_id": "en", "duration": 3.5, "speed": 1.0}
```

## Training

Training is launched with `accelerate`:
```bash
accelerate launch \
    --gpu_ids "0,1,2,3,4,5,6,7" \
    --num_processes 8 \
    -m omnivoice.cli.train \
    --train_config config/train_config_emilia.json \
    --data_config config/data_config_emilia.json \
    --output_dir exp/omnivoice_emilia
```

See `examples/` for end-to-end scripts (`run_emilia.sh`, `run_finetune.sh`, `run_eval.sh`) and `examples/config/` for ready-to-use JSON configs (including a DeepSpeed ZeRO-2 config and an `sdpa`-compatible fine-tune config).

**Key training config fields** (`omnivoice/training/config.py` → `TrainingConfig`):
- `llm_name_or_path`: base LLM (default `Qwen/Qwen3-0.6B`)
- `attn_implementation`: `"flex_attention"` (default, requires Ampere+ GPU) or `"sdpa"` (broader compatibility)
- `init_from_checkpoint`: for fine-tuning from a pretrained checkpoint
- `resume_from_checkpoint`: for resuming interrupted training
- `batch_tokens`: total token budget per GPU per step
- `audio_codebook_weights`: per-codebook loss weights (default `[8,8,6,6,4,4,2,2]`)
- `drop_cond_ratio`: probability of dropping all conditioning (default `0.1`)

Config is JSON-driven; load via `TrainingConfig.from_json(path)`.

## Data Pipeline

1. Raw data is JSONL manifests: `{"id", "audio_path", "text", "language_id"}`
2. Audio is tokenized into WebDataset shards via `omnivoice/scripts/extract_audio_tokens.py`
3. The manifest for training (`data.lst`) format: `/path/to/data.tar /path/to/label.jsonl num_items num_seconds`
4. During training, `OmniVoiceSampleProcessor` (`omnivoice/data/processor.py`) converts samples to model inputs: masking, prompt selection, language/instruct token injection, optional pinyin

Other scripts in `omnivoice/scripts/`: `jsonl_to_webdataset.py`, `denoise_audio.py`, `extract_audio_tokens_add_noise.py` (for prompt denoising training).

## Architecture Overview

- **`omnivoice/models/omnivoice.py`** — Core model. `OmniVoice` wraps a HuggingFace `PreTrainedModel` (the LLM backbone) with audio codebook embeddings. `OmniVoice.from_pretrained()` loads the model; `model.generate()` runs inference; `model.forward()` computes training loss. Key config: `OmniVoiceGenerationConfig` (num_step, guidance_scale, t_shift, layer_penalty_factor, position_temperature, class_temperature).
- **`omnivoice/training/`** — `TrainingConfig` (JSON-driven config), `OmniTrainer` (Accelerate-based training loop), `builder.py` (data pipeline assembly), `checkpoint.py` (save/resume with TensorBoard logging).
- **`omnivoice/data/`** — `dataset.py` (WebDataset/JSONL loading, `MuxWebDatasetReader` for weighted multilingual mixing), `processor.py` (sample preprocessing), `collator.py` (`PackingDataCollator` for flex_attention vs. `PaddingDataCollator` for sdpa), `batching.py` (sequence packing for `flex_attention` vs. length-grouped padding for `sdpa`).
- **`omnivoice/utils/`** — Audio I/O (`audio.py`), text chunking (`text.py`), duration estimation (`duration.py`, script-aware per language family), language ID mapping (`lang_map.py`, 600+ languages from `docs/lang_id_name_map.tsv`), voice design attribute validation (`voice_design.py`).
- **`omnivoice/eval/`** — Metrics: WER (multiple ASR backends: SenseVoice, FLEURS, HuBERT, MiniMax, SeedTTS), speaker similarity (ECAPA-TDNN + WavLM), UTMOS MOS scoring. Requires `pip install omnivoice[eval]`.

## Webapp

A FastAPI + Alpine.js SPA lives in `webapp/` for voice cloning via browser UI.

- `webapp/main.py` — REST API: `GET /api/health`, voice sample CRUD at `/api/samples/*`, synthesis endpoint with speed control
- `webapp/engine.py` — Lazy-loading inference engine with thread-safe generation; auto-detects device/dtype (CUDA fp16, CPU fp32); caches `VoiceClonePrompt` objects
- `webapp/store.py` — Persistent voice storage: `webapp/data/voices.json` + `webapp/data/audio/{uuid}.wav`; auto-converts non-WAV uploads via pydub/ffmpeg

**Run with Docker (recommended):**
```bash
docker compose up --build
```
Requires 1 NVIDIA GPU. Mounts `./webapp/data` for persistence and a named `hf-cache` volume for model downloads. Env var `MODEL_NAME` defaults to `k2-fsa/OmniVoice`.

**Cloudflare Tunnel** (`cloudflare/config.yml`): maps `voice.vietngoquang.com` → `http://tts-app:8000`. Replace `<TUNNEL_UUID>` with actual tunnel UUID and provide `cloudflare/credentials.json` (gitignored) before deploying.

## Key Design Details

- Audio is encoded at 24 kHz with 8 codebooks using HiggsAudioV2 (vocab size 1025, mask token ID 1024); the model operates on multi-codebook token sequences interleaved with text tokens.
- Long inputs are chunked (`audio_chunk_threshold=30s`) and cross-faded during inference.
- `flex_attention` uses sequence packing (all samples concatenated, shape `[1, C, T]`); `sdpa` uses length-grouped padding (shape `[B, C, max_len]`). These are incompatible — switching backends requires changing the training config and restarting.
- Intel Arc GPUs (XPU backend) are supported but fall back to `sdpa` (no `flex_attention` support on XPU).
- `HF_ENDPOINT="https://hf-mirror.com"` can be set if HuggingFace is unreachable for model downloads.
- Batch inference (`omnivoice-infer-batch`) separates voice-clone samples from instruct/auto samples to avoid mode mixing within a batch.
