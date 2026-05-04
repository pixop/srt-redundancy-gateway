# Publishing images to Docker Hub

This directory includes a release helper flow:

- `release.env.example` - release configuration template
- `docker-release.sh` - multi-arch build and push for all release images
- `../Makefile` targets: `make release-dry-run`, `make release`

Release order in `docker-release.sh`:

1. `tsduck-tools` (base runtime with `tsp`, `tsswitch`, SRT plugin)
2. `tsduck-gateway` (inherits from `tsduck-tools`)
3. `health-watchdog`

## 1) Configure release variables

```bash
cp scripts/release.env.example scripts/release.env
```

Set at least:

- `DOCKER_NAMESPACE`
- `RELEASE_TAG`

Optional but recommended:

- `GIT_SHA_TAG`
- `PUSH_LATEST=true`
- `TSDUCK_TAG`

## 2) Login to Docker Hub

```bash
docker login
```

## 3) Preview commands

```bash
make release-dry-run
```

## 4) Build and push

```bash
make release
```

The script pushes:

- `${DOCKER_NAMESPACE}/srt-redundancy-gateway-tsduck:<tag>`
- `${DOCKER_NAMESPACE}/srt-redundancy-gateway-watchdog:<tag>`
- `${DOCKER_NAMESPACE}/srt-redundancy-gateway-tsduck-tools:<tag>`

It can also push SHA and `latest` tags based on `scripts/release.env`.
