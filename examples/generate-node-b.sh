#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${TARGET_PORT:-7002}"
PID="${PID:-400}"

echo "[generate-node-b] sending craft TS to srt://${TARGET_HOST}:${TARGET_PORT}"
exec tsp \
  -I craft --pid "${PID}" \
  -P regulate \
  -O srt --caller "${TARGET_HOST}:${TARGET_PORT}" --transtype live --messageapi
