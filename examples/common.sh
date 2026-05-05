#!/usr/bin/env bash

# When example scripts run via dockerized tsp, use the input-gateway container
# namespace so 127.0.0.1 resolves to the gateway listeners.
ensure_input_gateway_namespace_for_dockerized_tsp() {
  if ! command -v tsp >/dev/null 2>&1; then
    export TSDUCK_TOOLS_DOCKER_NETWORK="${TSDUCK_TOOLS_DOCKER_NETWORK:-container:srt-input-gateway}"
  fi
}
