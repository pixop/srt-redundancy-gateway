# srt-redundancy-gateway

Reusable live MPEG-TS over SRT redundancy middleware built with TSDuck.

This repository provides two Dockerized gateway patterns:

1. Input redundancy gateway (primary/backup ingest -> single selected output)
2. Output redundancy gateway (node A/node B outputs -> single selected output with watchdog control)

The rest of your media pipeline consumes one stable SRT endpoint and remains
unchanged.

## Architecture overview

### Input redundancy

- `tsswitch` receives two SRT listener inputs (primary and backup).
- Primary input is preferred (`--primary-input 0`).
- On packet timeout (`--receive-timeout`), `tsswitch` selects backup.
- One selected SRT listener output is exposed downstream.
- `tsswitch --event-udp` events can be exported and observed by an event-only observer service.

### Output redundancy

- `tsswitch` receives two SRT caller inputs (node A and node B).
- A Python watchdog polls health endpoints for node A and node B.
- Watchdog sends UDP remote-control commands to `tsswitch` (`--remote`).
- Hysteresis thresholds avoid flapping.
- `tsswitch --event-udp` events are consumed by watchdog for active-input observability.

## Why `-I fork` around SRT legs

SRT sessions are connection-oriented. A disconnect can otherwise look like an
end-of-input lifecycle event to `tsswitch` in long-running failover scenarios.
Wrapping each leg in `-I fork "tsp -I srt ... -O file -"` makes each leg
restartable and improves reconnect behavior for listener/caller workflows.

## Repository layout

- `docker/tsduck-gateway/Dockerfile` - gateway image with TSDuck tools
- `docker/tsduck-tools/Dockerfile` - standalone TSDuck tools image for local generators
- `docker/health-watchdog/Dockerfile` - watchdog image
- `gateway/commands/input-failover.sh` - input redundancy command wrapper
- `gateway/commands/output-failover.sh` - output redundancy command wrapper
- `watchdog/watchdog.py` - health polling + hysteresis + remote control + metrics/traces
- `compose/input-failover.yml` - input failover deployment
- `compose/output-failover.yml` - output failover deployment
- `compose/observability.yml` - shared Prometheus/OTel/Tempo/Grafana stack
- `examples/` - local fake SRT source scripts

## Quick start

1. Create env file:

```bash
cp .env.example .env
```

2. Build local `tsduck-tools` base image (required for local gateway builds):

```bash
docker build -f docker/tsduck-tools/Dockerfile -t srt-redundancy-gateway-tsduck-tools:local .
```

3. Start input failover gateway:

```bash
docker compose -f compose/input-failover.yml up --build
```

Alternative one-command demo startup (includes a dummy downstream consumer):

```bash
make up-input-demo
```

4. Start a downstream consumer (keeps output listener active during tests):

```bash
bash examples/consume-input-output.sh
```

5. In separate terminals, feed test streams:

```bash
bash examples/generate-primary.sh
bash examples/generate-backup.sh
```

6. Simulate primary failure by stopping `generate-primary.sh` and verify output
   remains available on `${INPUT_FAILOVER_OUTPUT_LISTEN_PORT}`.

## Output failover quick start

1. Launch gateway and watchdog:

```bash
docker compose -f compose/output-failover.yml up --build
```

2. Feed node outputs:

```bash
TSDUCK_TOOLS_IMAGE=<namespace>/srt-redundancy-gateway-tsduck-tools:<tag> bash examples/generate-node-a.sh
TSDUCK_TOOLS_IMAGE=<namespace>/srt-redundancy-gateway-tsduck-tools:<tag> bash examples/generate-node-b.sh
```

3. Point node health endpoints in `.env`:

- `NODE_A_HEALTH_URL`
- `NODE_B_HEALTH_URL`

4. Make node A unhealthy long enough to cross `WATCHDOG_BAD_THRESHOLD`; watchdog
   switches to node B if node B is stably healthy.

## SRT encryption and per-leg flags

Use per-direction/per-leg env vars to add SRT plugin arguments without editing
scripts:

- Input shared for both ingest legs:
  - `INPUT_SRT_SOURCE_COMMON_FLAGS`
- Input leg-specific overrides:
  - `INPUT_SRT_PRIMARY_EXTRA_FLAGS`
  - `INPUT_SRT_BACKUP_EXTRA_FLAGS`
- Input selected output listener:
  - `INPUT_SRT_OUTPUT_EXTRA_FLAGS`
- Output side shared for node A/B callers:
  - `OUTPUT_SRT_SOURCE_COMMON_FLAGS`
- Output node-specific overrides:
  - `OUTPUT_SRT_NODE_A_EXTRA_FLAGS`
  - `OUTPUT_SRT_NODE_B_EXTRA_FLAGS`
- Output selected output listener:
  - `OUTPUT_SRT_OUTPUT_EXTRA_FLAGS`

Example:

```bash
# Identical input-side credentials for primary + backup.
INPUT_SRT_SOURCE_COMMON_FLAGS="--multiple --transtype live --messageapi --passphrase input-secret --pbkeylen 16"

# Different credentials on output side for each upstream node.
OUTPUT_SRT_NODE_A_EXTRA_FLAGS="--passphrase node-a-secret --pbkeylen 16"
OUTPUT_SRT_NODE_B_EXTRA_FLAGS="--passphrase node-b-secret --pbkeylen 16"
```

## Prometheus and OpenTelemetry

Enable observability with the shared compose overlay:

```bash
docker compose -f compose/output-failover.yml -f compose/observability.yml --profile observability up --build
```

Included:

- Watchdog Prometheus endpoint: `http://127.0.0.1:9108/metrics`
- Input event observer endpoint: `http://127.0.0.1:9109/metrics` (when enabled)
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000` (admin/admin)
- OTEL Collector receiver: `127.0.0.1:4318` (HTTP), `127.0.0.1:4317` (gRPC)
- Tempo API: `http://127.0.0.1:3200`

Grafana is auto-provisioned with:

- Prometheus datasource (`http://127.0.0.1:9090`)
- Tempo datasource (`http://127.0.0.1:3200`)
- starter dashboard: `SRT Redundancy Overview`

Key watchdog metrics:

- `watchdog_uptime_seconds`
- `gateway_active_input`
- `gateway_waiting_for_input`
- `gateway_last_switch_unixtime`
- `watchdog_switch_commands_total`
- `watchdog_switch_events_total`
- `watchdog_event_type_total{event_type=...}`
- `watchdog_node_health`
- `watchdog_health_checks_total`
- `watchdog_health_check_latency_seconds`

For input gateway-only observability (no controller watchdog), run:

```bash
docker compose -f compose/input-failover.yml -f compose/observability.yml --profile observability up --build
```

To run both input and output gateways on one host with shared observability:

```bash
docker compose -f compose/input-failover.yml -f compose/output-failover.yml -f compose/observability.yml --profile observability up --build
```

Or via Makefile shortcuts:

```bash
make up-both-observability
make down-both-observability
```

This starts:

- `input-gateway` (emits `--event-udp` to `${INPUT_EVENT_UDP_HOST}:${INPUT_EVENT_UDP_PORT}`)
- `input-event-observer` (listens on `${INPUT_EVENT_UDP_PORT}` and exports metrics on `:9109`)

Note: in input observer mode, `gateway_waiting_for_input` can be inferred from
rapid input flapping with:
`INPUT_OBSERVER_WAITING_FLAP_WINDOW_SEC` and
`INPUT_OBSERVER_WAITING_FLAP_THRESHOLD`.

## Local test instructions

### Input gateway continuity check

- Start `compose/input-failover.yml`.
- Start `examples/consume-input-output.sh` to attach a downstream receiver on `:6000`.
- Start both `examples/generate-primary.sh` and `examples/generate-backup.sh`.
- Consume output from `srt://127.0.0.1:${INPUT_FAILOVER_OUTPUT_LISTEN_PORT}`.
- Stop primary generator and confirm stream continuity from backup.

### Output gateway controlled switch check

- Start `compose/output-failover.yml`.
- Start both node generators.
- Start built-in mock health services with profile:

```bash
docker compose -f compose/output-failover.yml --profile demo-health up --build
```

Makefile shortcut:

```bash
make up-output-demo-health
```

- Flip node A to unhealthy:

```bash
bash examples/set-health.sh 18081 unhealthy
```

- Restore node A:

```bash
bash examples/set-health.sh 18081 healthy
```

- Flip node A to unhealthy and keep node B healthy.
- Confirm switch occurs only after bad threshold.
- Recover node A and verify preferred failback after good threshold.

## Production notes

- Keep ports/envs explicit; avoid hardcoded node-specific assumptions.
- Use host networking for operational simplicity in SRT-heavy environments.
- `tsduck-tools` image builds TSDuck from source (pinned tag in Dockerfile); first build can take several minutes.
- Keep health checks cheap and deterministic.
- Tune `WATCHDOG_GOOD_THRESHOLD` / `WATCHDOG_BAD_THRESHOLD` to your jitter profile.
- Consider adding node-exporter/cAdvisor if container/system-level telemetry is required.

## Docker image publishing

For Docker Hub publishing steps, see `scripts/README.md`.

## Troubleshooting

- `generate-primary.sh` times out on `srt_connect`:
  - Ensure a downstream consumer is connected first (`bash examples/consume-input-output.sh`), or run `make up-input-demo`.
  - Recreate cleanly: `docker compose -f compose/input-failover.yml down && docker compose -f compose/input-failover.yml up --build`.
  - Verify gateway logs include the `tsswitch` startup line and no rapid restarts.

## Limitations (v1)

- No Kubernetes manifests yet.
- OTel traces are wired for export, but advanced sampling/tail-based processing is not configured.
