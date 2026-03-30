#!/usr/bin/env bash
set -euo pipefail

export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_URL="${OLLAMA_URL:-http://host.docker.internal:11434/api/generate}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-tinyllama}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama is not installed. Install Ollama first."
  exit 1
fi

if ! ss -ltn | grep -q ":11434"; then
  echo "Starting local Ollama on ${OLLAMA_HOST}..."
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  sleep 2
fi

echo "Ensuring model ${OLLAMA_MODEL} is present..."
ollama pull "${OLLAMA_MODEL}"

echo "Rebuilding and recreating Docker services..."
docker-compose down --remove-orphans || true
docker-compose up -d --build --force-recreate

echo "Done."
