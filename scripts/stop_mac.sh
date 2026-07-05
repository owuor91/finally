#!/usr/bin/env bash
# Stop and remove the FinAlly container. Leaves the data volume intact. Idempotent.
set -euo pipefail

CONTAINER="finally"

docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "Stopped and removed '$CONTAINER'." \
  || echo "'$CONTAINER' is not running."
echo "Data volume 'finally-data' preserved."
