#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"

TARGET_HOST="${TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${TARGET_PORT:-5010}"
PID="${PID:-200}"

ensure_input_gateway_namespace_for_dockerized_tsp

echo "[generate-backup] sending craft TS to srt://${TARGET_HOST}:${TARGET_PORT}"
exec "${SCRIPT_DIR}/run-tsp.sh" \
  -I craft --pid "${PID}" \
  -P regulate \
  -O srt --caller "${TARGET_HOST}:${TARGET_PORT}" --transtype live --messageapi
