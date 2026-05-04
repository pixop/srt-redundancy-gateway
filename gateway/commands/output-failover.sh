#!/usr/bin/env bash
set -euo pipefail

NODE_A_HOST="${NODE_A_HOST:-127.0.0.1}"
NODE_A_PORT="${NODE_A_PORT:-7001}"
NODE_B_HOST="${NODE_B_HOST:-127.0.0.1}"
NODE_B_PORT="${NODE_B_PORT:-7002}"
OUTPUT_LISTEN_PORT="${OUTPUT_FAILOVER_OUTPUT_LISTEN_PORT:-8000}"
RECEIVE_TIMEOUT_MS="${OUTPUT_FAILOVER_RECEIVE_TIMEOUT_MS:-2000}"
REMOTE_HOST="${TSSWITCH_REMOTE_HOST:-127.0.0.1}"
REMOTE_PORT="${TSSWITCH_REMOTE_PORT:-4444}"
ALLOW_HOST="${TSSWITCH_ALLOW_HOST:-127.0.0.1}"
EVENT_UDP_HOST="${TSSWITCH_EVENT_UDP_HOST:-127.0.0.1}"
EVENT_UDP_PORT="${TSSWITCH_EVENT_UDP_PORT:-5556}"
VERBOSE="${OUTPUT_FAILOVER_VERBOSE:-1}"

TSSWITCH_ARGS=()
if [[ "${VERBOSE}" == "1" ]]; then
  TSSWITCH_ARGS+=("-v")
fi

# In caller mode, wrapping the SRT source with -I fork keeps each leg
# independently restartable after network/peer interruptions.
CMD=(
  tsswitch
  "${TSSWITCH_ARGS[@]}"
  --fast-switch
  --primary-input 0
  --receive-timeout "${RECEIVE_TIMEOUT_MS}"
  --infinite
  --remote "${REMOTE_HOST}:${REMOTE_PORT}"
  --allow "${ALLOW_HOST}"
  --event-udp "${EVENT_UDP_HOST}:${EVENT_UDP_PORT}"
  --event-user-data "srt-redundancy-gateway"
  -I
  fork
  "tsp -I srt --caller ${NODE_A_HOST}:${NODE_A_PORT} --transtype live --messageapi -O file -"
  -I
  fork
  "tsp -I srt --caller ${NODE_B_HOST}:${NODE_B_PORT} --transtype live --messageapi -O file -"
  -O
  srt
  --listener
  "0.0.0.0:${OUTPUT_LISTEN_PORT}"
  --multiple
  --transtype
  live
  --messageapi
)

echo "[output-failover] Starting command:"
printf '  %q' "${CMD[@]}"
echo

exec "${CMD[@]}"
