.PHONY: build-tsduck-tools-local up-input-demo down-input-demo up-output-demo-health down-output-demo-health up-input-observability down-input-observability up-output-observability down-output-observability up-both-observability down-both-observability release release-dry-run

build-tsduck-tools-local:
	docker build -f docker/tsduck-tools/Dockerfile -t srt-redundancy-gateway-tsduck-tools:local .

up-input-demo:
	docker compose -f compose/input-failover.yml --profile demo-consumer up --build

down-input-demo:
	docker compose -f compose/input-failover.yml --profile demo-consumer down

up-output-demo-health:
	docker compose -f compose/output-failover.yml --profile demo-health up --build

down-output-demo-health:
	docker compose -f compose/output-failover.yml --profile demo-health down

up-input-observability:
	docker compose -f compose/input-failover.yml -f compose/observability.yml --profile observability up --build

down-input-observability:
	docker compose -f compose/input-failover.yml -f compose/observability.yml --profile observability down

up-output-observability:
	docker compose -f compose/output-failover.yml -f compose/observability.yml --profile observability up --build

down-output-observability:
	docker compose -f compose/output-failover.yml -f compose/observability.yml --profile observability down

up-both-observability:
	docker compose -f compose/input-failover.yml -f compose/output-failover.yml -f compose/observability.yml --profile observability up --build

down-both-observability:
	docker compose -f compose/input-failover.yml -f compose/output-failover.yml -f compose/observability.yml --profile observability down

release:
	bash scripts/docker-release.sh

release-dry-run:
	bash scripts/docker-release.sh --dry-run
