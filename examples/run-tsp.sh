#!/usr/bin/env bash
set -euo pipefail

# If tsp exists locally, use it directly.
if command -v tsp >/dev/null 2>&1; then
  exec tsp "$@"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "tsp not found locally and docker is unavailable."
  echo "Install TSDuck locally or use Docker with TSDUCK_TOOLS_IMAGE."
  exit 1
fi

TSDUCK_TOOLS_IMAGE="${TSDUCK_TOOLS_IMAGE:-srt-redundancy-gateway-tsduck-tools:local}"
TSDUCK_TOOLS_DOCKER_PULL="${TSDUCK_TOOLS_DOCKER_PULL:-false}"
TSDUCK_TOOLS_DOCKER_NETWORK="${TSDUCK_TOOLS_DOCKER_NETWORK:-host}"

if [[ "${TSDUCK_TOOLS_DOCKER_PULL}" == "true" ]]; then
  docker pull "${TSDUCK_TOOLS_IMAGE}" >/dev/null
fi

echo "[run-tsp] local tsp not found, using docker image ${TSDUCK_TOOLS_IMAGE}"
exec docker run --rm --network "${TSDUCK_TOOLS_DOCKER_NETWORK}" "${TSDUCK_TOOLS_IMAGE}" "$@"
