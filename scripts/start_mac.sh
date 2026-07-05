#!/usr/bin/env bash
# Build (if needed) and run the FinAlly container. Idempotent.
# Usage: ./scripts/start_mac.sh [--build]
set -euo pipefail

IMAGE="finally"
CONTAINER="finally"
PORT="8000"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and add your keys:"
  echo "  cp .env.example .env"
  exit 1
fi

# Build if the image is missing or --build was passed.
if [ "${1:-}" = "--build" ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building image '$IMAGE'..."
  docker build -t "$IMAGE" .
fi

# Replace any existing container so re-runs are safe.
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

docker run -d --name "$CONTAINER" \
  -p "${PORT}:8000" \
  --env-file .env \
  -v finally-data:/app/db \
  "$IMAGE"

URL="http://localhost:${PORT}"
echo "FinAlly is running at ${URL}"
command -v open >/dev/null 2>&1 && open "$URL" || true
