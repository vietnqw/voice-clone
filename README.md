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

## Development

To run the app locally without Docker:

**1. Install dependencies**

```bash
pip install uv
uv sync --extra webapp
```

**2. Run the server**

```bash
uvicorn webapp.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000`. The `--reload` flag auto-restarts the server on code changes.

> The first run downloads the OmniVoice model (~2 GB) from HuggingFace and caches it in `~/.cache/huggingface/`.

**Environment variables**

| Variable | Default | Description |
|---|---|---|
| `MODEL_NAME` | `k2-fsa/OmniVoice` | HuggingFace model ID |
| `DATA_DIR` | `webapp/data` | Directory for voice metadata and audio files |
| `HF_ENDPOINT` | _(unset)_ | Set to `https://hf-mirror.com` if HuggingFace is unreachable |

## Cloudflare Tunnel (optional)

To expose the app over HTTPS via a [remotely-managed Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/):

1. In the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels → Create a tunnel**.
2. Choose **Cloudflared**, give it a name, then under **Install connector** select **Docker** and copy the token from the command shown.
3. Under **Public Hostname**, add a route: subdomain `voice`, your domain, service type `HTTP`, URL `tts-app:8000`.
4. Create a `.env` file in the project root:
   ```
   CLOUDFLARE_TUNNEL_TOKEN=your_token_here
   ```
5. Run `docker compose up -d` — the `cloudflared` service connects automatically alongside the app.

## Data Persistence

Voice samples are stored in `webapp/data/` (mounted as a Docker volume):

```
webapp/data/
├── voices.json       # voice metadata
└── audio/            # uploaded audio files
```
