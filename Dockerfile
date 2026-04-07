# Multi-stage Dockerfile for ai-video-cutter
# Targets: api | worker
#
# Build:
#   docker build --target api -t vc-api .
#   docker build --target worker -t vc-worker .
#
# Or use docker compose (recommended):
#   docker compose up --build

# ── Base: system deps + Python packages ──────────────────────────────────────
FROM python:3.11-slim AS base

# ffmpeg and libgl1 (OpenCV headless requires libglib2.0-0)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies before copying source so layer is cached.
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[api,worker]"

# Copy source and config.
COPY src/ ./src/
COPY config/ ./config/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# ── API service ───────────────────────────────────────────────────────────────
FROM base AS api

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ── Worker service (queue specified at runtime via --queues flag) ─────────────
FROM base AS worker

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel", "info"]
