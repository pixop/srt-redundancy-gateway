# Example stream generators

These scripts use TSDuck to generate deterministic fake TS payloads and push
them over SRT for local failover tests.

If `tsp` is not installed on your host, scripts automatically run `tsp`
from a Docker image via `run-tsp.sh`.

- default image: `srt-redundancy-gateway-tsduck-tools:local`
- override image: `TSDUCK_TOOLS_IMAGE=<namespace>/srt-redundancy-gateway-tsduck-tools:<tag>`
- force image pull before run: `TSDUCK_TOOLS_DOCKER_PULL=true`
- override docker network mode: `TSDUCK_TOOLS_DOCKER_NETWORK=host` (or `container:<name>`)

For input failover generators, when local `tsp` is missing they default to:

- `TSDUCK_TOOLS_DOCKER_NETWORK=container:srt-input-gateway`

This makes `127.0.0.1:5000` and `127.0.0.1:5010` target the actual gateway
listener namespace directly.

For output failover scripts, dockerized `tsp` defaults to host networking so
`127.0.0.1:7001`, `:7002`, and `:8000` stay in the same namespace as the
host-network output gateway.

- `generate-primary.sh` -> primary input listener (default `:5000`)
- `generate-backup.sh` -> backup input listener (default `:5010`)
- `generate-node-a.sh` -> output failover node A caller target (default `:7001`)
- `generate-node-b.sh` -> output failover node B caller target (default `:7002`)
- `consume-input-output.sh` -> dummy downstream consumer for input gateway output (`:6000`)
- `consume-output-output.sh` -> dummy downstream consumer for output gateway output (`:8000`)
- `mock-health-service.py` -> tiny controllable HTTP health endpoint
- `set-health.sh` -> helper to flip mock health state

Run from repository root:

```bash
TSDUCK_TOOLS_IMAGE=<namespace>/srt-redundancy-gateway-tsduck-tools:<tag> \
bash examples/generate-primary.sh
TSDUCK_TOOLS_IMAGE=<namespace>/srt-redundancy-gateway-tsduck-tools:<tag> \
bash examples/generate-backup.sh
TSDUCK_TOOLS_IMAGE=<namespace>/srt-redundancy-gateway-tsduck-tools:<tag> \
bash examples/generate-node-a.sh
TSDUCK_TOOLS_IMAGE=<namespace>/srt-redundancy-gateway-tsduck-tools:<tag> \
bash examples/generate-node-b.sh
```

For input failover tests, start a downstream consumer first:

```bash
bash examples/consume-input-output.sh
```

Run two local mock health endpoints (for watchdog demos):

```bash
MOCK_HEALTH_PORT=18081 python examples/mock-health-service.py
MOCK_HEALTH_PORT=18082 python examples/mock-health-service.py
```

Flip mock node health:

```bash
bash examples/set-health.sh 18081 unhealthy
bash examples/set-health.sh 18081 healthy
```
