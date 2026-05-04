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
- `gateway/commands/input-failover.sh` - input redundancy command wrapper
- `gateway/commands/output-failover.sh` - output redundancy command wrapper
- `docker/health-watchdog/Dockerfile` - watchdog image
- `watchdog/watchdog.py` - health polling + hysteresis + remote control + metrics/traces
- `compose/input-failover.yml` - input failover deployment
- `compose/output-failover.yml` - output failover deployment (+ watchdog)
- `compose/combined-example.yml` - both patterns together
- `examples/` - local fake SRT source scripts

## Quick start

1. Create env file:

```bash
cp .env.example .env
```

2. Start input failover gateway:

```bash
docker compose -f compose/input-failover.yml up --build
```

3. In separate terminals, feed test streams:

```bash
bash examples/generate-primary.sh
bash examples/generate-backup.sh
```

4. Simulate primary failure by stopping `generate-primary.sh` and verify output
   remains available on `${INPUT_FAILOVER_OUTPUT_LISTEN_PORT}`.

## Output failover quick start

1. Launch gateway and watchdog:

```bash
docker compose -f compose/output-failover.yml up --build
```

2. Feed node outputs:

```bash
bash examples/generate-node-a.sh
bash examples/generate-node-b.sh
```

3. Point node health endpoints in `.env`:

- `NODE_A_HEALTH_URL`
- `NODE_B_HEALTH_URL`

4. Make node A unhealthy long enough to cross `WATCHDOG_BAD_THRESHOLD`; watchdog
   switches to node B if node B is stably healthy.

## Prometheus and OpenTelemetry

Enable observability profile in output/combined compose:

```bash
docker compose -f compose/output-failover.yml --profile observability up --build
```

Included:

- Watchdog Prometheus endpoint: `http://127.0.0.1:9108/metrics`
- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000` (admin/admin)
- OTEL Collector receiver: `127.0.0.1:4318` (HTTP), `127.0.0.1:4317` (gRPC)
- Tempo API: `http://127.0.0.1:3200`

Grafana is auto-provisioned with:

- Prometheus datasource (`http://127.0.0.1:9090`)
- Tempo datasource (`http://127.0.0.1:3200`)
- starter dashboard: `SRT Redundancy Overview`

Key watchdog metrics:

- `gateway_active_input`
- `gateway_last_switch_unixtime`
- `watchdog_switch_commands_total`
- `watchdog_switch_events_total`
- `watchdog_node_health`
- `watchdog_health_checks_total`
- `watchdog_health_check_latency_seconds`

## Local test instructions

### Input gateway continuity check

- Start `compose/input-failover.yml`.
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
- Keep health checks cheap and deterministic.
- Tune `WATCHDOG_GOOD_THRESHOLD` / `WATCHDOG_BAD_THRESHOLD` to your jitter profile.
- Consider adding node-exporter/cAdvisor if container/system-level telemetry is required.

## Limitations (v1)

- No Kubernetes manifests yet.
- No built-in mock health service container in compose.
- Grafana datasource/dashboards are not auto-provisioned yet (manual setup).
