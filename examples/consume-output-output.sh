#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"

TARGET_HOST="${TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${TARGET_PORT:-8000}"

if ! command -v tsp >/dev/null 2>&1; then
  export TSDUCK_TOOLS_DOCKER_NETWORK="${TSDUCK_TOOLS_DOCKER_NETWORK:-host}"
fi

echo "[consume-output-output] receiving from srt://${TARGET_HOST}:${TARGET_PORT}"
exec "${SCRIPT_DIR}/run-tsp.sh" \
  -I srt --caller "${TARGET_HOST}:${TARGET_PORT}" --transtype live --messageapi \
  -O drop
