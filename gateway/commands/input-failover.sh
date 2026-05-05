#!/usr/bin/env bash
set -euo pipefail

PRIMARY_LISTEN_PORT="${PRIMARY_LISTEN_PORT:-5000}"
BACKUP_LISTEN_PORT="${BACKUP_LISTEN_PORT:-5010}"
OUTPUT_LISTEN_PORT="${INPUT_FAILOVER_OUTPUT_LISTEN_PORT:-6000}"
RECEIVE_TIMEOUT_MS="${INPUT_FAILOVER_RECEIVE_TIMEOUT_MS:-2000}"
VERBOSE="${INPUT_FAILOVER_VERBOSE:-1}"
INPUT_EVENT_UDP_HOST="${INPUT_EVENT_UDP_HOST:-127.0.0.1}"
INPUT_EVENT_UDP_PORT="${INPUT_EVENT_UDP_PORT:-5557}"
INPUT_EVENT_USER_DATA="${INPUT_EVENT_USER_DATA:-input-failover}"
INPUT_SRT_SOURCE_COMMON_FLAGS="${INPUT_SRT_SOURCE_COMMON_FLAGS:---multiple --transtype live --messageapi}"
INPUT_SRT_PRIMARY_EXTRA_FLAGS="${INPUT_SRT_PRIMARY_EXTRA_FLAGS:-}"
INPUT_SRT_BACKUP_EXTRA_FLAGS="${INPUT_SRT_BACKUP_EXTRA_FLAGS:-}"
INPUT_SRT_OUTPUT_EXTRA_FLAGS="${INPUT_SRT_OUTPUT_EXTRA_FLAGS:---multiple --transtype live --messageapi}"

TSSWITCH_ARGS=()
if [[ "${VERBOSE}" == "1" ]]; then
  TSSWITCH_ARGS+=("-v")
fi
read -r -a INPUT_SRT_OUTPUT_EXTRA_FLAGS_ARR <<< "${INPUT_SRT_OUTPUT_EXTRA_FLAGS}"

# Wrap SRT listeners with -I fork + tsp so each leg can restart
# independently after disconnects. This avoids listener-session end-of-stream
# behavior from permanently retiring a leg inside long-running failover setups.
CMD=(
  tsswitch
  "${TSSWITCH_ARGS[@]}"
  --fast-switch
  --primary-input 0
  --receive-timeout "${RECEIVE_TIMEOUT_MS}"
  --infinite
  --event-udp "${INPUT_EVENT_UDP_HOST}:${INPUT_EVENT_UDP_PORT}"
  --event-user-data "${INPUT_EVENT_USER_DATA}"
  -I
  fork
  "tsp -I srt --listener :${PRIMARY_LISTEN_PORT} ${INPUT_SRT_SOURCE_COMMON_FLAGS} ${INPUT_SRT_PRIMARY_EXTRA_FLAGS} -O file -"
  -I
  fork
  "tsp -I srt --listener :${BACKUP_LISTEN_PORT} ${INPUT_SRT_SOURCE_COMMON_FLAGS} ${INPUT_SRT_BACKUP_EXTRA_FLAGS} -O file -"
  -O
  srt
  --listener
  ":${OUTPUT_LISTEN_PORT}"
  "${INPUT_SRT_OUTPUT_EXTRA_FLAGS_ARR[@]}"
)

echo "[input-failover] Starting command:"
printf '  %q' "${CMD[@]}"
echo

exec "${CMD[@]}"
