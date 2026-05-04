FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG TSTAG=v3.43-4549
ARG PREFIX=/usr/local

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    locales \
    # Runtime deps
    libedit2 libcurl4 libpcap0.8 libssl3 zlib1g libzstd1 libsrt1.5-openssl \
    # Build deps
    build-essential git pkg-config python3 python3-dev \
    libedit-dev libcurl4-openssl-dev libpcap-dev libssl-dev \
    zlib1g-dev libzstd-dev libsrt-openssl-dev && \
    locale-gen en_US.UTF-8 && update-locale LANG=en_US.UTF-8

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

WORKDIR /opt/tsduck
RUN git clone --depth 1 --branch "${TSTAG}" https://github.com/tsduck/tsduck.git .

RUN make -j"$(nproc)" NOTEST=true NOQT=1 NODOC=1 NOGITHUB=1 NOVATEK=1 NODEKTEC=1
RUN make install PREFIX="${PREFIX}" NOTEST=true NOQT=1 NODOC=1 NOGITHUB=1 NOVATEK=1 NODEKTEC=1

RUN apt-get purge -y --auto-remove \
    build-essential git pkg-config python3-dev \
    libedit-dev libcurl4-openssl-dev libpcap-dev libssl-dev \
    zlib1g-dev libzstd-dev libsrt-openssl-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /opt/tsduck

ENV PATH="${PREFIX}/bin:${PATH}" \
    LD_LIBRARY_PATH="${PREFIX}/lib:${LD_LIBRARY_PATH}"

RUN tsversion --version=all && tsp -I srt --help >/dev/null

ENTRYPOINT ["tsp"]
