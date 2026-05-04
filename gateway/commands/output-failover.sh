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
  :"${OUTPUT_LISTEN_PORT}"
  --multiple
  --transtype
  live
  --messageapi
)

echo "[output-failover] Starting command:"
printf '  %q' "${CMD[@]}"
echo

exec "${CMD[@]}"
#!/usr/bin/env bash
set -euo pipefail

if [[ "${COMMAND_DEBUG:-true}" == "true" ]]; then
  set -x
fi

NODE_A_HOST="${NODE_A_HOST:-127.0.0.1}"
NODE_A_PORT="${NODE_A_PORT:-7001}"
NODE_B_HOST="${NODE_B_HOST:-127.0.0.1}"
NODE_B_PORT="${NODE_B_PORT:-7002}"
OUTPUT_LISTEN_PORT="${OUTPUT_LISTEN_PORT:-8000}"
OUTPUT_RECEIVE_TIMEOUT_MS="${OUTPUT_RECEIVE_TIMEOUT_MS:-2000}"
OUTPUT_PRIMARY_INDEX="${OUTPUT_PRIMARY_INDEX:-0}"
OUTPUT_FAST_SWITCH="${OUTPUT_FAST_SWITCH:-true}"
OUTPUT_INFINITE="${OUTPUT_INFINITE:-true}"
TSSWITCH_REMOTE_HOST="${TSSWITCH_REMOTE_HOST:-127.0.0.1}"
TSSWITCH_REMOTE_PORT="${TSSWITCH_REMOTE_PORT:-4444}"
TSSWITCH_ALLOW_HOST="${TSSWITCH_ALLOW_HOST:-127.0.0.1}"
TSSWITCH_EVENT_UDP_TARGET="${TSSWITCH_EVENT_UDP_TARGET:-127.0.0.1:4545}"
TSSWITCH_EVENT_USER_DATA="${TSSWITCH_EVENT_USER_DATA:-output-failover}"
SRT_COMMON_FLAGS="${SRT_COMMON_FLAGS:---multiple --transtype live --messageapi}"

FAST_SWITCH_ARGS=()
if [[ "${OUTPUT_FAST_SWITCH}" == "true" ]]; then
  FAST_SWITCH_ARGS+=(--fast-switch)
fi

INFINITE_ARGS=()
if [[ "${OUTPUT_INFINITE}" == "true" ]]; then
  INFINITE_ARGS+=(--infinite)
fi

# Important: wrapping caller legs in -I fork isolates each SRT session and
# keeps reconnect behavior predictable under source churn.
exec tsswitch \
  -v \
  "${FAST_SWITCH_ARGS[@]}" \
  --primary-input "${OUTPUT_PRIMARY_INDEX}" \
  --receive-timeout "${OUTPUT_RECEIVE_TIMEOUT_MS}" \
  "${INFINITE_ARGS[@]}" \
  --remote "${TSSWITCH_REMOTE_HOST}:${TSSWITCH_REMOTE_PORT}" \
  --allow "${TSSWITCH_ALLOW_HOST}" \
  --event-udp "${TSSWITCH_EVENT_UDP_TARGET}" \
  --event-user-data "${TSSWITCH_EVENT_USER_DATA}" \
  -I fork "tsp -I srt --caller ${NODE_A_HOST}:${NODE_A_PORT} --transtype live --messageapi -O file -" \
  -I fork "tsp -I srt --caller ${NODE_B_HOST}:${NODE_B_PORT} --transtype live --messageapi -O file -" \
  -O srt --listener ":${OUTPUT_LISTEN_PORT}" ${SRT_COMMON_FLAGS}
