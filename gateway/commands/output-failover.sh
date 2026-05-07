#!/usr/bin/env bash
set -euo pipefail

NODE_A_PORT="${NODE_A_PORT:-7001}"
NODE_B_PORT="${NODE_B_PORT:-7002}"
OUTPUT_LISTEN_PORT="${OUTPUT_FAILOVER_OUTPUT_LISTEN_PORT:-8000}"
RECEIVE_TIMEOUT_MS="${OUTPUT_FAILOVER_RECEIVE_TIMEOUT_MS:-2000}"
REMOTE_HOST="${TSSWITCH_REMOTE_HOST:-127.0.0.1}"
REMOTE_PORT="${TSSWITCH_REMOTE_PORT:-4444}"
ALLOW_HOST="${TSSWITCH_ALLOW_HOST:-127.0.0.1}"
EVENT_UDP_HOST="${TSSWITCH_EVENT_UDP_HOST:-127.0.0.1}"
EVENT_UDP_PORT="${TSSWITCH_EVENT_UDP_PORT:-5556}"
VERBOSE="${OUTPUT_FAILOVER_VERBOSE:-1}"
OUTPUT_SRT_STATS_INTERVAL_MS="${OUTPUT_SRT_STATS_INTERVAL_MS:-5000}"
OUTPUT_SRT_SOURCE_COMMON_FLAGS="${OUTPUT_SRT_SOURCE_COMMON_FLAGS:---multiple --transtype live --messageapi}"
OUTPUT_SRT_NODE_A_EXTRA_FLAGS="${OUTPUT_SRT_NODE_A_EXTRA_FLAGS:-}"
OUTPUT_SRT_NODE_B_EXTRA_FLAGS="${OUTPUT_SRT_NODE_B_EXTRA_FLAGS:-}"
OUTPUT_SRT_OUTPUT_EXTRA_FLAGS="${OUTPUT_SRT_OUTPUT_EXTRA_FLAGS:---multiple --transtype live --messageapi}"

TSSWITCH_ARGS=()
if [[ "${VERBOSE}" == "1" ]]; then
  TSSWITCH_ARGS+=("-v")
fi
read -r -a OUTPUT_SRT_OUTPUT_EXTRA_FLAGS_ARR <<< "${OUTPUT_SRT_OUTPUT_EXTRA_FLAGS}"

emit_srt_stats_event() {
  local leg="$1"
  local direction="$2"
  local json_payload="$3"
  printf '{"event":"srtstats","gateway":"output","leg":"%s","direction":"%s","stats":%s}\n' \
    "${leg}" "${direction}" "${json_payload}" >"/dev/udp/${EVENT_UDP_HOST}/${EVENT_UDP_PORT}" || true
}

forward_stats_from_logs() {
  local prefix="$1"
  local leg="$2"
  local direction="$3"
  local line="$4"
  if [[ "${line}" == *"${prefix}"* ]]; then
    local json_payload="${line#*"${prefix}"}"
    emit_srt_stats_event "${leg}" "${direction}" "${json_payload}"
  fi
}

# Wrap each SRT listener leg with -I fork so disconnected/idle sessions can
# restart independently without retiring the leg inside long-running failover.
CMD=(
  tsswitch
  "${TSSWITCH_ARGS[@]}"
  --fast-switch
  --receive-timeout "${RECEIVE_TIMEOUT_MS}"
  --infinite
  --remote "${REMOTE_HOST}:${REMOTE_PORT}"
  --allow "${ALLOW_HOST}"
  --event-udp "${EVENT_UDP_HOST}:${EVENT_UDP_PORT}"
  --event-user-data "srt-redundancy-gateway"
  -I
  fork
  "tsp -I srt --listener :${NODE_A_PORT} ${OUTPUT_SRT_SOURCE_COMMON_FLAGS} ${OUTPUT_SRT_NODE_A_EXTRA_FLAGS} --statistics-interval ${OUTPUT_SRT_STATS_INTERVAL_MS} --json-line=SRTSTATS_OUTPUT_NODE_A: -O file -"
  -I
  fork
  "tsp -I srt --listener :${NODE_B_PORT} ${OUTPUT_SRT_SOURCE_COMMON_FLAGS} ${OUTPUT_SRT_NODE_B_EXTRA_FLAGS} --statistics-interval ${OUTPUT_SRT_STATS_INTERVAL_MS} --json-line=SRTSTATS_OUTPUT_NODE_B: -O file -"
  -O
  srt
  --listener
  ":${OUTPUT_LISTEN_PORT}"
  --statistics-interval
  "${OUTPUT_SRT_STATS_INTERVAL_MS}"
  --json-line=SRTSTATS_OUTPUT_OUTPUT:
  "${OUTPUT_SRT_OUTPUT_EXTRA_FLAGS_ARR[@]}"
)

echo "[output-failover] Starting command:"
printf '  %q' "${CMD[@]}"
echo

"${CMD[@]}" 2> >(
  while IFS= read -r line; do
    echo "${line}" >&2
    forward_stats_from_logs "SRTSTATS_OUTPUT_NODE_A:" "node_a" "in" "${line}"
    forward_stats_from_logs "SRTSTATS_OUTPUT_NODE_B:" "node_b" "in" "${line}"
    forward_stats_from_logs "SRTSTATS_OUTPUT_OUTPUT:" "output" "out" "${line}"
  done
)
