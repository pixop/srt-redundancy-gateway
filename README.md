# srt-redundancy-gateway

Dockerized MPEG-TS over SRT redundancy gateways built with TSDuck.

## Architecture

### Input failover (`compose/input-failover.yml`)

- `tsswitch` listens on `PRIMARY_LISTEN_PORT` and `BACKUP_LISTEN_PORT`.
- Input `0` is preferred (`--primary-input 0`); failover happens on receive timeout.
- Selected output is exposed on `INPUT_FAILOVER_OUTPUT_LISTEN_PORT`.
- `--event-udp` events can be consumed by `input-event-observer` (observability profile).

### Output failover (`compose/output-failover.yml`)

- `tsswitch` listens on `NODE_A_PORT` and `NODE_B_PORT`; selected output is exposed on `OUTPUT_FAILOVER_OUTPUT_LISTEN_PORT`.
- `watchdog/watchdog.py` polls `NODE_A_HEALTH_URL` and `NODE_B_HEALTH_URL` (optional regex matchers).
- Watchdog controls `tsswitch` over UDP remote commands and reads `--event-udp` events.
- Policy: prefer A; switch to B only when A is stably unhealthy and B is stably healthy; fail back when A is stably healthy.

Both gateways wrap SRT legs with `-I fork "tsp -I srt ... -O file -"` so dropped sessions can restart without retiring a leg.

## Setup

```bash
cp .env.example .env
```

Optional (only if `tsp` is not installed locally and you run `examples/*.sh`):

```bash
make build-tsduck-tools-local
```

## Input failover demo

```bash
make up-input-demo
```

Generate traffic:

```bash
bash examples/generate-primary.sh
bash examples/generate-backup.sh
```

Verify failover by stopping `generate-primary.sh`; output remains available on `INPUT_FAILOVER_OUTPUT_LISTEN_PORT`.

## Output failover demo

```bash
make up-output-demo-health
```

Generate traffic and consume output:

```bash
bash examples/generate-node-a.sh
bash examples/generate-node-b.sh
bash examples/consume-output-output.sh
```

Trigger node A health changes:

```bash
bash examples/set-health.sh 18081 unhealthy
bash examples/set-health.sh 18081 healthy
```

## Bridge connectors (output mode)

Enable:

```bash
docker compose -f compose/output-failover.yml --profile bridge-connectors up --build
```

Relevant envs:

- `BRIDGE_A_SOURCE_HOST` / `BRIDGE_A_SOURCE_PORT`
- `BRIDGE_B_SOURCE_HOST` / `BRIDGE_B_SOURCE_PORT`
- `BRIDGE_A_TARGET_HOST` / `BRIDGE_A_TARGET_PORT`
- `BRIDGE_B_TARGET_HOST` / `BRIDGE_B_TARGET_PORT`

## SRT flag overrides

Input:

- `INPUT_SRT_SOURCE_COMMON_FLAGS`
- `INPUT_SRT_PRIMARY_EXTRA_FLAGS`
- `INPUT_SRT_BACKUP_EXTRA_FLAGS`
- `INPUT_SRT_OUTPUT_EXTRA_FLAGS`

Output:

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

Start both gateways with shared observability stack:

```bash
make up-all
```

Endpoints:

- Input observer metrics: `http://127.0.0.1:9107/metrics` (when input observability profile is enabled)
- Output watchdog metrics: `http://127.0.0.1:9108/metrics`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000` (`admin` / `admin`)
- Tempo: `http://127.0.0.1:3200`
- OTEL Collector: `127.0.0.1:4318` (HTTP), `127.0.0.1:4317` (gRPC)

Key metrics:

- `gateway_active_input`
- `gateway_waiting_for_input`
- `watchdog_switch_commands_total`
- `watchdog_switch_events_total`
- `watchdog_node_health`
- `watchdog_health_checks_total`
- `gateway_bytes_total`

## Publishing

See `scripts/README.md`.
