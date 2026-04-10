#!/usr/bin/env bash
set -e

# ── Environment setup ─────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example — fill in your API keys before continuing."
    exit 1
  else
    echo "No .env file found. Create one with at least GEMINI_API_KEY and an LLM provider key."
    exit 1
  fi
fi

# ── Local data directory ───────────────────────────────────────────────────────
mkdir -p local/data/projects

# ── Detect dev mode ───────────────────────────────────────────────────────────
COMPOSE_FILES="-f docker-compose.yml"
if [ "${1}" = "--dev" ]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.dev.yml"
  echo "Starting in development mode (Vite HMR on :5173)..."
  shift
  docker compose $COMPOSE_FILES up --build "$@"
else
  echo "Starting in production mode (frontend on :3001, API on :8000)..."
  docker compose $COMPOSE_FILES up --build -d "$@"
fi
