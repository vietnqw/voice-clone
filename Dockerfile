FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime

WORKDIR /app

# Install system deps: ffmpeg for audio format support
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy project metadata first (cache layer for deps)
COPY pyproject.toml ./

# Copy source
COPY omnivoice/ omnivoice/
COPY webapp/ webapp/

# Install all dependencies via uv pip
# (torch/torchaudio are already in the base image and satisfy >=2.4)
RUN uv pip install --system --no-cache -e ".[webapp]"

EXPOSE 8000

CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
