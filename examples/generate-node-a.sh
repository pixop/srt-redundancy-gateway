#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${TARGET_PORT:-7001}"
PID="${PID:-300}"

echo "[generate-node-a] sending craft TS to srt://${TARGET_HOST}:${TARGET_PORT}"
exec "$(dirname "$0")/run-tsp.sh" \
  -I craft --pid "${PID}" \
  -P regulate \
  -O srt --caller "${TARGET_HOST}:${TARGET_PORT}" --transtype live --messageapi
