.PHONY: build-tsduck-tools-local up-input-demo down-input-demo up-input-observability release release-dry-run

build-tsduck-tools-local:
	docker build -f docker/tsduck-tools/Dockerfile -t srt-redundancy-gateway-tsduck-tools:local .

up-input-demo:
	docker compose -f compose/input-failover.yml --profile demo-consumer up --build

down-input-demo:
	docker compose -f compose/input-failover.yml --profile demo-consumer down

up-input-observability:
	docker compose -f compose/input-failover.yml --profile observability up --build

release:
	bash scripts/docker-release.sh

release-dry-run:
	bash scripts/docker-release.sh --dry-run
