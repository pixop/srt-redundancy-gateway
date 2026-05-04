FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        tsduck \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY gateway /app/gateway

CMD ["bash", "-lc", "echo 'Use compose commands to select gateway mode'; sleep infinity"]
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
      iproute2 \
      netcat-openbsd \
      procps \
      tsduck && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY gateway/commands/input-failover.sh /app/commands/input-failover.sh
COPY gateway/commands/output-failover.sh /app/commands/output-failover.sh

RUN chmod +x /app/commands/input-failover.sh /app/commands/output-failover.sh

ENTRYPOINT ["/bin/bash"]
