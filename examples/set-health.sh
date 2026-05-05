#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <port> <healthy|unhealthy> [token]"
  exit 1
fi

PORT="$1"
STATE="$2"
TOKEN="${3:-${MOCK_HEALTH_TOKEN:-devtoken}}"

if [[ "${STATE}" == "healthy" ]]; then
  VALUE="true"
elif [[ "${STATE}" == "unhealthy" ]]; then
  VALUE="false"
else
  echo "state must be healthy or unhealthy"
  exit 1
fi

curl -sS -X POST "http://127.0.0.1:${PORT}/set?healthy=${VALUE}&token=${TOKEN}"
echo
