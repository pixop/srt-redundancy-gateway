#!/usr/bin/env bash
set -euo pipefail

PRIMARY_LISTEN_PORT="${PRIMARY_LISTEN_PORT:-5000}"
BACKUP_LISTEN_PORT="${BACKUP_LISTEN_PORT:-5010}"
OUTPUT_LISTEN_PORT="${INPUT_FAILOVER_OUTPUT_LISTEN_PORT:-6000}"
RECEIVE_TIMEOUT_MS="${INPUT_FAILOVER_RECEIVE_TIMEOUT_MS:-2000}"
VERBOSE="${INPUT_FAILOVER_VERBOSE:-1}"

TSSWITCH_ARGS=()
if [[ "${VERBOSE}" == "1" ]]; then
  TSSWITCH_ARGS+=("-v")
fi

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
  -I
  fork
  "tsp -I srt --listener :${PRIMARY_LISTEN_PORT} --multiple --transtype live --messageapi -O file -"
  -I
  fork
  "tsp -I srt --listener :${BACKUP_LISTEN_PORT} --multiple --transtype live --messageapi -O file -"
  -O
  srt
  --listener
  :"${OUTPUT_LISTEN_PORT}"
  --multiple
  --transtype
  live
  --messageapi
)

echo "[input-failover] Starting command:"
printf '  %q' "${CMD[@]}"
echo

exec "${CMD[@]}"
#!/usr/bin/env bash
set -euo pipefail

if [[ "${COMMAND_DEBUG:-true}" == "true" ]]; then
  set -x
fi

PRIMARY_LISTEN_PORT="${PRIMARY_LISTEN_PORT:-5000}"
BACKUP_LISTEN_PORT="${BACKUP_LISTEN_PORT:-5010}"
INPUT_OUTPUT_LISTEN_PORT="${INPUT_OUTPUT_LISTEN_PORT:-6000}"
INPUT_RECEIVE_TIMEOUT_MS="${INPUT_RECEIVE_TIMEOUT_MS:-2000}"
INPUT_PRIMARY_INDEX="${INPUT_PRIMARY_INDEX:-0}"
INPUT_FAST_SWITCH="${INPUT_FAST_SWITCH:-true}"
INPUT_INFINITE="${INPUT_INFINITE:-true}"
SRT_COMMON_FLAGS="${SRT_COMMON_FLAGS:---multiple --transtype live --messageapi}"

FAST_SWITCH_ARGS=()
if [[ "${INPUT_FAST_SWITCH}" == "true" ]]; then
  FAST_SWITCH_ARGS+=(--fast-switch)
fi

INFINITE_ARGS=()
if [[ "${INPUT_INFINITE}" == "true" ]]; then
  INFINITE_ARGS+=(--infinite)
fi

# Important: we wrap SRT listeners with -I fork + tsp so each input leg runs
# in an isolated subprocess and reconnect behavior remains reliable after peer
# disconnect/reconnect cycles.
exec tsswitch \
  -v \
  "${FAST_SWITCH_ARGS[@]}" \
  --primary-input "${INPUT_PRIMARY_INDEX}" \
  --receive-timeout "${INPUT_RECEIVE_TIMEOUT_MS}" \
  "${INFINITE_ARGS[@]}" \
  -I fork "tsp -I srt --listener :${PRIMARY_LISTEN_PORT} ${SRT_COMMON_FLAGS} -O file -" \
  -I fork "tsp -I srt --listener :${BACKUP_LISTEN_PORT} ${SRT_COMMON_FLAGS} -O file -" \
  -O srt --listener ":${INPUT_OUTPUT_LISTEN_PORT}" ${SRT_COMMON_FLAGS}
