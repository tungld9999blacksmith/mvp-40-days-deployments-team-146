#!/usr/bin/env bash
# =============================================================================
# dev-stack.sh — Dựng/điều khiển stack backend local cho P-146.
#
# 3 service: backend (FastAPI), mock-ev-system, redis.
#
# Cách dùng:
#   ./scripts/dev-stack.sh up        # build + chạy nền (mặc định)
#   ./scripts/dev-stack.sh down      # dừng + xoá container (giữ volume)
#   ./scripts/dev-stack.sh build     # chỉ build image
#   ./scripts/dev-stack.sh logs      # xem log realtime
#   ./scripts/dev-stack.sh ps        # trạng thái service
#   ./scripts/dev-stack.sh restart   # restart stack
#   ./scripts/dev-stack.sh clean     # down + xoá volume (mất dữ liệu)
# =============================================================================
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="docker-compose.dev.yaml"
ACTION="${1:-up}"

info() { printf '\033[36m[INFO]\033[0m  %s\n' "$*"; }
ok()   { printf '\033[32m[OK]\033[0m    %s\n' "$*"; }
die()  { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Chưa cài Docker. Xem https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || die "Docker daemon chưa chạy. Mở Docker Desktop rồi thử lại."
[[ -f "$REPO_ROOT/.env" ]] || die "Không tìm thấy .env ở gốc repo. Copy từ .env.example rồi điền giá trị."

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose -f "$COMPOSE_FILE")
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose -f "$COMPOSE_FILE")
else
  die "Không tìm thấy Docker Compose."
fi

case "$ACTION" in
  up)
    info "Build + khởi động stack (backend, mock-ev-system, redis)..."
    "${COMPOSE[@]}" up -d --build
    ok "Stack đã chạy:"
    "${COMPOSE[@]}" ps
    echo
    ok "Backend API   : http://localhost:8000/health   (docs: http://localhost:8000/docs)"
    ok "Mock EV system: http://localhost:8100/health   (docs: http://localhost:8100/docs)"
    ok "Redis         : localhost:6379"
    ;;
  down)    info "Dừng + xoá container (giữ volume)..."; "${COMPOSE[@]}" down; ok "Đã dừng." ;;
  build)   info "Build image..."; "${COMPOSE[@]}" build; ok "Build xong." ;;
  logs)    info "Log realtime (Ctrl+C để thoát)..."; "${COMPOSE[@]}" logs -f --tail=100 ;;
  ps)      "${COMPOSE[@]}" ps ;;
  restart) info "Restart stack..."; "${COMPOSE[@]}" restart; ok "Đã restart." ;;
  clean)   info "Down + xoá volume (mất dữ liệu)..."; "${COMPOSE[@]}" down -v; ok "Đã dọn sạch." ;;
  *)       die "Action không hợp lệ: $ACTION (up|down|build|logs|ps|restart|clean)" ;;
esac
