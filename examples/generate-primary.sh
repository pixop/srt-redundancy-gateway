#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${TARGET_PORT:-5000}"
PID="${PID:-100}"

if ! command -v tsp >/dev/null 2>&1; then
  # Run in the gateway container namespace so localhost targets the listener.
  export TSDUCK_TOOLS_DOCKER_NETWORK="${TSDUCK_TOOLS_DOCKER_NETWORK:-container:srt-input-gateway}"
fi

echo "[generate-primary] sending craft TS to srt://${TARGET_HOST}:${TARGET_PORT}"
exec "$(dirname "$0")/run-tsp.sh" \
  -I craft --pid "${PID}" \
  -P regulate \
  -O srt --caller "${TARGET_HOST}:${TARGET_PORT}" --transtype live --messageapi
