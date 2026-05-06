#!/usr/bin/env bash
set -euo pipefail

BRIDGE_NAME="${BRIDGE_NAME:-bridge}"
BRIDGE_KEY="${BRIDGE_KEY:-}"

resolve_bridge_var() {
  local generic_name="$1"
  local keyed_suffix="$2"
  local default_value="$3"
  local generic_value="${!generic_name:-}"
  if [[ -n "${generic_value}" ]]; then
    printf '%s' "${generic_value}"
    return
  fi
  if [[ -n "${BRIDGE_KEY}" ]]; then
    local keyed_name="BRIDGE_${BRIDGE_KEY}_${keyed_suffix}"
    local keyed_value="${!keyed_name:-}"
    if [[ -n "${keyed_value}" ]]; then
      printf '%s' "${keyed_value}"
      return
    fi
  fi
  printf '%s' "${default_value}"
}

SOURCE_HOST="$(resolve_bridge_var "BRIDGE_SOURCE_HOST" "SOURCE_HOST" "127.0.0.1")"
SOURCE_PORT="$(resolve_bridge_var "BRIDGE_SOURCE_PORT" "SOURCE_PORT" "7101")"
TARGET_HOST="$(resolve_bridge_var "BRIDGE_TARGET_HOST" "TARGET_HOST" "127.0.0.1")"
TARGET_PORT="$(resolve_bridge_var "BRIDGE_TARGET_PORT" "TARGET_PORT" "7001")"
VERBOSE="${BRIDGE_VERBOSE:-1}"
BRIDGE_SRT_COMMON_FLAGS="${BRIDGE_SRT_COMMON_FLAGS:---transtype live --messageapi}"
BRIDGE_SOURCE_EXTRA_FLAGS="$(resolve_bridge_var "BRIDGE_SOURCE_EXTRA_FLAGS" "SOURCE_EXTRA_FLAGS" "")"
BRIDGE_TARGET_EXTRA_FLAGS="$(resolve_bridge_var "BRIDGE_TARGET_EXTRA_FLAGS" "TARGET_EXTRA_FLAGS" "")"

CMD=(tsp)
if [[ "${VERBOSE}" == "1" ]]; then
  CMD+=("-v")
fi

read -r -a BRIDGE_SRT_COMMON_FLAGS_ARR <<< "${BRIDGE_SRT_COMMON_FLAGS}"
read -r -a BRIDGE_SOURCE_EXTRA_FLAGS_ARR <<< "${BRIDGE_SOURCE_EXTRA_FLAGS}"
read -r -a BRIDGE_TARGET_EXTRA_FLAGS_ARR <<< "${BRIDGE_TARGET_EXTRA_FLAGS}"

CMD+=(
  -I
  srt
  --caller
  "${SOURCE_HOST}:${SOURCE_PORT}"
  "${BRIDGE_SRT_COMMON_FLAGS_ARR[@]}"
  "${BRIDGE_SOURCE_EXTRA_FLAGS_ARR[@]}"
  -O
  srt
  --caller
  "${TARGET_HOST}:${TARGET_PORT}"
  "${BRIDGE_SRT_COMMON_FLAGS_ARR[@]}"
  "${BRIDGE_TARGET_EXTRA_FLAGS_ARR[@]}"
)

echo "[${BRIDGE_NAME}] Starting command:"
printf '  %q' "${CMD[@]}"
echo

exec "${CMD[@]}"
