#!/usr/bin/env bash
# =============================================================================
# infra-stack.sh — Chạy CHỈ hạ tầng phụ trợ (mock-ev-system, redis)
# bằng Docker, để backend FastAPI chạy trực tiếp bằng terminal (debug local).
#
# Backend KHÔNG nằm trong stack này. Sau khi hạ tầng lên:
#   cd backend && uv run uvicorn src.main:app --reload --port 8000
#
# Cách dùng:
#   ./scripts/infra-stack.sh up      # build + chạy nền (mặc định)
#   ./scripts/infra-stack.sh down    # dừng (giữ volume)
#   ./scripts/infra-stack.sh logs    # log realtime
#   ./scripts/infra-stack.sh ps      # trạng thái
#   ./scripts/infra-stack.sh clean   # down + xoá volume (mất dữ liệu)
# =============================================================================
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE_FILE="docker-compose.infra.yaml"
ACTION="${1:-up}"

info() { printf '\033[36m[INFO]\033[0m  %s\n' "$*"; }
ok()   { printf '\033[32m[OK]\033[0m    %s\n' "$*"; }
die()  { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Chưa cài Docker. Xem https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || die "Docker daemon chưa chạy. Mở Docker Desktop rồi thử lại."

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose -f "$COMPOSE_FILE")
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose -f "$COMPOSE_FILE")
else
  die "Không tìm thấy Docker Compose."
fi

case "$ACTION" in
  up)
    info "Build + khởi động hạ tầng (mock-ev-system, redis)..."
    "${COMPOSE[@]}" up -d --build
    ok "Hạ tầng đã chạy:"
    "${COMPOSE[@]}" ps
    echo
    ok "Mock EV system: http://localhost:8100/health"
    ok "Redis         : localhost:6379"
    echo
    info "Bước tiếp theo — chạy backend bằng terminal (KHÔNG dùng Docker):"
    echo "  1) copy .env.local-debug.example -> .env ở gốc repo (sửa OPENAI_API_KEY nếu cần)"
    echo "  2) cd backend"
    echo "  3) uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
    echo "     (hoặc, dùng venv/pip: uvicorn src.main:app --reload --port 8000)"
    ;;
  down)  info "Dừng container hạ tầng (giữ volume)..."; "${COMPOSE[@]}" down; ok "Đã dừng." ;;
  logs)  info "Log realtime (Ctrl+C để thoát)..."; "${COMPOSE[@]}" logs -f --tail=100 ;;
  ps)    "${COMPOSE[@]}" ps ;;
  clean) info "Down + xoá volume (mất dữ liệu)..."; "${COMPOSE[@]}" down -v; ok "Đã dọn sạch." ;;
  *)     die "Action không hợp lệ: $ACTION (up|down|logs|ps|clean)" ;;
esac
