# Voice Clone

A multilingual voice cloning web app powered by [OmniVoice](https://github.com/k2-fsa/OmniVoice). Upload a voice sample, then synthesize speech in 600+ languages using that voice.

## Prerequisites

- Docker & Docker Compose
- NVIDIA GPU with CUDA support
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

## Setup

**1. Clone the repo**

```bash
git clone git@github.com:vietnqw/voice-clone.git
cd voice-clone
```

**2. Start the app**

```bash
docker compose up --build
```

The first run downloads the OmniVoice model (~2 GB) from HuggingFace. Subsequent starts use the cached model.

Open `http://localhost:8000` in your browser.

> If HuggingFace is unreachable, set `HF_ENDPOINT=https://hf-mirror.com` in `docker-compose.yml`.

## Cloudflare Tunnel (optional)

To expose the app over HTTPS via Cloudflare Tunnel:

1. [Create a tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/) in the Cloudflare dashboard and download the credentials file.
2. Place it at `cloudflare/credentials.json`.
3. In `cloudflare/config.yml`, replace `<TUNNEL_UUID>` with your tunnel's UUID and update the hostname.
4. Run `docker compose up` — the `cloudflared` service starts automatically alongside the app.

## Data Persistence

Voice samples are stored in `webapp/data/` (mounted as a Docker volume):

```
webapp/data/
├── voices.json       # voice metadata
└── audio/            # uploaded audio files
```
