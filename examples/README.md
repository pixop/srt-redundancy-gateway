# Example stream generators

These scripts use TSDuck to generate deterministic fake TS payloads and push
them over SRT for local failover tests.

- `generate-primary.sh` -> primary input listener (default `:5000`)
- `generate-backup.sh` -> backup input listener (default `:5010`)
- `generate-node-a.sh` -> output failover node A caller target (default `:7001`)
- `generate-node-b.sh` -> output failover node B caller target (default `:7002`)
- `mock-health-service.py` -> tiny controllable HTTP health endpoint
- `set-health.sh` -> helper to flip mock health state

Run from repository root:

```bash
bash examples/generate-primary.sh
bash examples/generate-backup.sh
bash examples/generate-node-a.sh
bash examples/generate-node-b.sh
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
