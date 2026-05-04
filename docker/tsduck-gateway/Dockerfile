ARG TSDUCK_TOOLS_IMAGE=srt-redundancy-gateway-tsduck-tools:local
FROM ${TSDUCK_TOOLS_IMAGE}

WORKDIR /app
COPY gateway /app/gateway

# Reset the tools image entrypoint ("tsp"), otherwise gateway commands are
# interpreted as tsp CLI parameters.
ENTRYPOINT []

CMD ["bash", "-lc", "echo 'Use compose commands to select gateway mode'; sleep infinity"]
