#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${TARGET_PORT:-6000}"

if ! command -v tsp >/dev/null 2>&1; then
  # Attach to gateway namespace to ensure localhost resolution is exact.
  export TSDUCK_TOOLS_DOCKER_NETWORK="${TSDUCK_TOOLS_DOCKER_NETWORK:-container:srt-input-gateway}"
fi

echo "[consume-input-output] receiving from srt://${TARGET_HOST}:${TARGET_PORT}"
exec "$(dirname "$0")/run-tsp.sh" \
  -I srt --caller "${TARGET_HOST}:${TARGET_PORT}" --transtype live --messageapi \
  -O drop
