#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"

TARGET_HOST="${TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${TARGET_PORT:-8000}"

ensure_host_network_for_dockerized_tsp

echo "[consume-output-output] receiving from srt://${TARGET_HOST}:${TARGET_PORT}"
exec "${SCRIPT_DIR}/run-tsp.sh" \
  -I srt --caller "${TARGET_HOST}:${TARGET_PORT}" --transtype live --messageapi \
  -O drop
