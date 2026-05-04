#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${SCRIPT_DIR}/release.env"
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

DOCKER_NAMESPACE="${DOCKER_NAMESPACE:-}"
TSDUCK_IMAGE_NAME="${TSDUCK_IMAGE_NAME:-srt-redundancy-gateway-tsduck}"
WATCHDOG_IMAGE_NAME="${WATCHDOG_IMAGE_NAME:-srt-redundancy-gateway-watchdog}"
TSDUCK_TOOLS_IMAGE_NAME="${TSDUCK_TOOLS_IMAGE_NAME:-srt-redundancy-gateway-tsduck-tools}"
RELEASE_TAG="${RELEASE_TAG:-}"
GIT_SHA_TAG="${GIT_SHA_TAG:-}"
PUSH_LATEST="${PUSH_LATEST:-false}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
TSDUCK_TAG="${TSDUCK_TAG:-v3.43-4549}"
PROJECT_ROOT="${PROJECT_ROOT:-${REPO_ROOT}}"

usage() {
  cat <<'EOF'
Usage:
  scripts/docker-release.sh [--dry-run]

Requirements:
  - docker buildx available
  - docker login completed
  - scripts/release.env configured (or equivalent env vars exported)
EOF
}

DRY_RUN=false
if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
elif [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
elif [[ $# -gt 0 ]]; then
  echo "Unknown argument: $1"
  usage
  exit 1
fi

if [[ -z "${DOCKER_NAMESPACE}" ]]; then
  echo "DOCKER_NAMESPACE is required. Set it in scripts/release.env."
  exit 1
fi

if [[ -z "${RELEASE_TAG}" ]]; then
  echo "RELEASE_TAG is required. Set it in scripts/release.env."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required."
  exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
  echo "docker buildx is required."
  exit 1
fi

TSDUCK_BASE="${DOCKER_NAMESPACE}/${TSDUCK_IMAGE_NAME}"
WATCHDOG_BASE="${DOCKER_NAMESPACE}/${WATCHDOG_IMAGE_NAME}"
TSDUCK_TOOLS_BASE="${DOCKER_NAMESPACE}/${TSDUCK_TOOLS_IMAGE_NAME}"

TSDUCK_TAG_ARGS=(-t "${TSDUCK_BASE}:${RELEASE_TAG}")
WATCHDOG_TAG_ARGS=(-t "${WATCHDOG_BASE}:${RELEASE_TAG}")
TSDUCK_TOOLS_TAG_ARGS=(-t "${TSDUCK_TOOLS_BASE}:${RELEASE_TAG}")

if [[ -n "${GIT_SHA_TAG}" ]]; then
  TSDUCK_TAG_ARGS+=(-t "${TSDUCK_BASE}:${GIT_SHA_TAG}")
  WATCHDOG_TAG_ARGS+=(-t "${WATCHDOG_BASE}:${GIT_SHA_TAG}")
  TSDUCK_TOOLS_TAG_ARGS+=(-t "${TSDUCK_TOOLS_BASE}:${GIT_SHA_TAG}")
fi

if [[ "${PUSH_LATEST}" == "true" ]]; then
  TSDUCK_TAG_ARGS+=(-t "${TSDUCK_BASE}:latest")
  WATCHDOG_TAG_ARGS+=(-t "${WATCHDOG_BASE}:latest")
  TSDUCK_TOOLS_TAG_ARGS+=(-t "${TSDUCK_TOOLS_BASE}:latest")
fi

echo "Release configuration:"
echo "  namespace:      ${DOCKER_NAMESPACE}"
echo "  release tag:    ${RELEASE_TAG}"
echo "  sha tag:        ${GIT_SHA_TAG:-<disabled>}"
echo "  push latest:    ${PUSH_LATEST}"
echo "  platforms:      ${PLATFORMS}"
echo "  tsduck tag:     ${TSDUCK_TAG}"
echo "  project root:   ${PROJECT_ROOT}"
echo
echo "Image outputs:"
for ((i = 0; i < ${#TSDUCK_TAG_ARGS[@]}; i += 2)); do
  echo "  - ${TSDUCK_TAG_ARGS[i + 1]}"
done
for ((i = 0; i < ${#WATCHDOG_TAG_ARGS[@]}; i += 2)); do
  echo "  - ${WATCHDOG_TAG_ARGS[i + 1]}"
done
for ((i = 0; i < ${#TSDUCK_TOOLS_TAG_ARGS[@]}; i += 2)); do
  echo "  - ${TSDUCK_TOOLS_TAG_ARGS[i + 1]}"
done
echo

build_cmd_tsduck=(
  docker buildx build
  --platform "${PLATFORMS}"
  --push
  --build-arg "TSDUCK_TOOLS_IMAGE=${TSDUCK_TOOLS_BASE}:${RELEASE_TAG}"
  -f "${PROJECT_ROOT}/docker/tsduck-gateway/Dockerfile"
  "${TSDUCK_TAG_ARGS[@]}"
  "${PROJECT_ROOT}"
)

build_cmd_watchdog=(
  docker buildx build
  --platform "${PLATFORMS}"
  --push
  -f "${PROJECT_ROOT}/docker/health-watchdog/Dockerfile"
  "${WATCHDOG_TAG_ARGS[@]}"
  "${PROJECT_ROOT}"
)

build_cmd_tsduck_tools=(
  docker buildx build
  --platform "${PLATFORMS}"
  --push
  --build-arg "TSTAG=${TSDUCK_TAG}"
  -f "${PROJECT_ROOT}/docker/tsduck-tools/Dockerfile"
  "${TSDUCK_TOOLS_TAG_ARGS[@]}"
  "${PROJECT_ROOT}"
)

echo "About to run:"
printf '  %q ' "${build_cmd_tsduck_tools[@]}"
echo
printf '  %q ' "${build_cmd_tsduck[@]}"
echo
printf '  %q ' "${build_cmd_watchdog[@]}"
echo

if [[ "${DRY_RUN}" == "true" ]]; then
  echo
  echo "Dry-run mode enabled, no build/push executed."
  exit 0
fi

"${build_cmd_tsduck_tools[@]}"
"${build_cmd_tsduck[@]}"
"${build_cmd_watchdog[@]}"

echo
echo "Release complete."
