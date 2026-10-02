#!/usr/bin/env bash
# =============================================================================
# build-backend-railway.sh — build (and optionally run / smoke-test) the images
# Railway deploys, so build errors show up locally before `railway up`:
#   backend : services `backend` + `worker` (dockerfiles/Dockerfile.railway)
#   mock    : service `mock-ev-system` (backend/mock-ev-system/Dockerfile.railway)
# See docs/deployments/RAILWAY_BACKEND_DEPLOYMENT.MD. Requires Docker running.
#
# Usage:
#   ./scripts/build-backend-railway.sh build [backend|mock]  # build the image only
#   ./scripts/build-backend-railway.sh run   [backend|mock]  # build + run (Ctrl+C to stop)
#   ./scripts/build-backend-railway.sh smoke [backend|mock]  # build + run detached + GET /health + stop
#
# Default target: backend (port 8000, tag p146-backend:railway); mock uses port
# 8100, tag p146-mock-ev-system:railway. `run` and `smoke` pass the repo-root
# .env to the backend container (--env-file) when it exists.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

info() { printf '\033[36m[INFO]\033[0m  %s\n' "$*"; }
ok()   { printf '\033[32m[OK]\033[0m    %s\n' "$*"; }
err()  { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; }

ACTION="${1:-build}"
TARGET="${2:-backend}"

env_args=()
case "$TARGET" in
  backend)
    DOCKERFILE="dockerfiles/Dockerfile.railway"; CONTEXT="."
    TAG="p146-backend:railway"; PORT="${PORT:-8000}"
    if [[ -f .env ]]; then env_args=(--env-file .env); fi
    ;;
  mock)
    DOCKERFILE="backend/mock-ev-system/Dockerfile.railway"; CONTEXT="backend"
    TAG="p146-mock-ev-system:railway"; PORT="${PORT:-8100}"
    ;;
  *)
    err "Unknown target: $TARGET (backend | mock)"
    exit 1
    ;;
esac
CONTAINER="p146-${TARGET}-railway-smoke"

build() {
  docker info >/dev/null 2>&1 || { err "Docker is not running"; exit 1; }
  info "Building $TAG from $DOCKERFILE (context: $CONTEXT)"
  docker build -f "$DOCKERFILE" -t "$TAG" "$CONTEXT"
  ok "Built $TAG"
}

case "$ACTION" in
  build)
    build
    ;;
  run)
    build
    info "Running $TAG on http://localhost:$PORT (Ctrl+C to stop)"
    docker run --rm -it -p "$PORT:$PORT" -e PORT="$PORT" "${env_args[@]}" "$TAG"
    ;;
  smoke)
    build
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    trap 'docker rm -f "$CONTAINER" >/dev/null 2>&1 || true' EXIT
    docker run -d --name "$CONTAINER" -p "$PORT:$PORT" -e PORT="$PORT" "${env_args[@]}" "$TAG" >/dev/null
    info "Waiting for http://localhost:$PORT/health"
    for _ in $(seq 1 30); do
      if curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then
        ok "/health returned 200"
        exit 0
      fi
      if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]]; then
        break
      fi
      sleep 2
    done
    err "/health did not return 200 — container logs:"
    docker logs --tail 50 "$CONTAINER" >&2 || true
    exit 1
    ;;
  *)
    err "Unknown action: $ACTION (build | run | smoke)"
    exit 1
    ;;
esac
