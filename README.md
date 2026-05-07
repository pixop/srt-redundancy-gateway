# srt-redundancy-gateway

Dockerized MPEG-TS over SRT redundancy gateways built with TSDuck.

This repo exposes one stable downstream SRT endpoint while handling upstream
path failures in front of it.

## What is implemented

- Input failover gateway (primary + backup ingest -> one selected output).
- Output failover gateway (node A + node B ingest -> one selected output).
- Python watchdog for output failover health polling and controlled switching.
- Optional bridge connectors for output mode.
- Optional observability stack (Prometheus, Grafana, OTEL Collector, Tempo).

## Architecture

### Input failover (`compose/input-failover.yml`)

- `tsswitch` listens on two SRT inputs (`PRIMARY_LISTEN_PORT`, `BACKUP_LISTEN_PORT`).
- Input `0` is preferred (`--primary-input 0`).
- On receive timeout, traffic switches to backup.
- Selected stream is exposed as one SRT listener (`INPUT_FAILOVER_OUTPUT_LISTEN_PORT`).
- `--event-udp` emits switch/events; optional `input-event-observer` consumes those events and exports metrics.

### Output failover (`compose/output-failover.yml`)

- `tsswitch` listens on two SRT inputs (`NODE_A_PORT`, `NODE_B_PORT`) and exposes one SRT listener output (`OUTPUT_FAILOVER_OUTPUT_LISTEN_PORT`).
- `watchdog/watchdog.py` polls `NODE_A_HEALTH_URL` and `NODE_B_HEALTH_URL` (with optional body regex checks).
- Watchdog sends UDP remote commands to `tsswitch` (`--remote`) and tracks active input from `--event-udp` events.
- Policy is A-preferred: switch to B only when A is stably unhealthy and B is stably healthy; fail back to A when A becomes stably healthy.

### Why `-I fork` is used

Each SRT leg is wrapped with `-I fork "tsp -I srt ... -O file -"` so a dropped
session can restart independently without permanently retiring the leg.

## Quick start

1) Create local env file:

```bash
cp .env.example .env
```

2) Build local tools image (used by `examples/run-tsp.sh` when `tsp` is not installed locally):

```bash
make build-tsduck-tools-local
```

## Run input failover demo

Single-command demo (gateway + demo consumer profile):

```bash
make up-input-demo
```

Manual mode:

```bash
docker compose -f compose/input-failover.yml up --build
bash examples/consume-input-output.sh
bash examples/generate-primary.sh
bash examples/generate-backup.sh
```

Then stop `generate-primary.sh` and confirm continuity on `INPUT_FAILOVER_OUTPUT_LISTEN_PORT`.

## Run output failover demo

Start gateway + watchdog + mock health services:

```bash
make up-output-demo-health
```

Feed both legs and consume output:

```bash
bash examples/generate-node-a.sh
bash examples/generate-node-b.sh
bash examples/consume-output-output.sh
```

Trigger health changes:

```bash
bash examples/set-health.sh 18081 unhealthy
bash examples/set-health.sh 18081 healthy
```

## Optional bridge connectors (output mode)

When upstream processing nodes expose their own SRT listeners, enable bridge containers:

```bash
docker compose -f compose/output-failover.yml --profile bridge-connectors up --build
```

Main bridge envs:

- `BRIDGE_A_SOURCE_HOST` / `BRIDGE_A_SOURCE_PORT`
- `BRIDGE_B_SOURCE_HOST` / `BRIDGE_B_SOURCE_PORT`
- `BRIDGE_A_TARGET_HOST` / `BRIDGE_A_TARGET_PORT` (defaults to gateway leg A)
- `BRIDGE_B_TARGET_HOST` / `BRIDGE_B_TARGET_PORT` (defaults to gateway leg B)

## SRT option overrides

Use env vars to inject SRT plugin flags without editing scripts.

Input mode:

- `INPUT_SRT_SOURCE_COMMON_FLAGS`
- `INPUT_SRT_PRIMARY_EXTRA_FLAGS`
- `INPUT_SRT_BACKUP_EXTRA_FLAGS`
- `INPUT_SRT_OUTPUT_EXTRA_FLAGS`

Output mode:

- `OUTPUT_SRT_SOURCE_COMMON_FLAGS`
- `OUTPUT_SRT_NODE_A_EXTRA_FLAGS`
- `OUTPUT_SRT_NODE_B_EXTRA_FLAGS`
- `OUTPUT_SRT_OUTPUT_EXTRA_FLAGS`

Example:

```bash
INPUT_SRT_SOURCE_COMMON_FLAGS="--multiple --transtype live --messageapi --passphrase input-secret --pbkeylen 16"
OUTPUT_SRT_NODE_A_EXTRA_FLAGS="--passphrase node-a-secret --pbkeylen 16"
OUTPUT_SRT_NODE_B_EXTRA_FLAGS="--passphrase node-b-secret --pbkeylen 16"
```

## Observability

Run a gateway plus the shared observability stack:

```bash
docker compose -f compose/output-failover.yml -f compose/observability.yml --profile observability up --build
```

Or run both gateways with one shared stack:

```bash
make up-all
```

Endpoints:

- Input observer metrics: `http://127.0.0.1:9107/metrics` (when input observability profile is enabled)
- Output watchdog metrics: `http://127.0.0.1:9108/metrics`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000` (`admin` / `admin`)
- OTEL Collector: `127.0.0.1:4318` (HTTP), `127.0.0.1:4317` (gRPC)
- Tempo: `http://127.0.0.1:3200`

Common watchdog metrics:

- `gateway_active_input`
- `gateway_waiting_for_input`
- `watchdog_switch_commands_total`
- `watchdog_switch_events_total`
- `watchdog_node_health`
- `watchdog_health_checks_total`
- `gateway_bytes_total`

## Production notes

- Services run with host networking; keep ports explicit and unique per host.
- Tune `WATCHDOG_GOOD_THRESHOLD` and `WATCHDOG_BAD_THRESHOLD` for your stream jitter profile.

## Publishing

Docker image publishing workflow lives in `scripts/README.md`.
