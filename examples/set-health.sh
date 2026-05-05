#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <port> <healthy|unhealthy> [token]"
  exit 1
fi

PORT="$1"
STATE="$2"

# Resolve token priority:
# 1) explicit 3rd arg
# 2) current shell env MOCK_HEALTH_TOKEN
# 3) project .env MOCK_HEALTH_TOKEN (if present)
# 4) fallback devtoken
TOKEN="${3:-${MOCK_HEALTH_TOKEN:-}}"
if [[ -z "${TOKEN}" ]] && [[ -f "${REPO_ROOT}/.env" ]]; then
  while IFS= read -r line; do
    if [[ "${line}" == MOCK_HEALTH_TOKEN=* ]]; then
      TOKEN="${line#MOCK_HEALTH_TOKEN=}"
    fi
  done < "${REPO_ROOT}/.env"
fi
TOKEN="${TOKEN:-devtoken}"

if [[ "${STATE}" == "healthy" ]]; then
  VALUE="true"
elif [[ "${STATE}" == "unhealthy" ]]; then
  VALUE="false"
else
  echo "state must be healthy or unhealthy"
  exit 1
fi

RESPONSE="$(curl -fsS -X POST "http://127.0.0.1:${PORT}/set?healthy=${VALUE}&token=${TOKEN}")"
echo "${RESPONSE}"
