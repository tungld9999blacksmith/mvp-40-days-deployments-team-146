#!/bin/bash
#!/usr/bin/env bash
# =============================================================================
# compose.local.sh - Build các image trong docker-compose.local.yaml
#
# Cách dùng:
#   ./compose.local.sh --dry-run                       # chỉ kiểm tra, không build
#   ./compose.local.sh --build                         # build thật
#   ./compose.local.sh --build -e path/to/other.env    # chỉ định file .env khác
#   ./compose.local.sh --build -- --no-cache           # truyền thêm option cho `compose build`
#
# Lưu ý: script tự chuyển về thư mục chứa nó, nên đường dẫn tương đối
#        (compose file, env file, logs) đều tính từ thư mục này.
# =============================================================================

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

readonly COMPOSE_FILE="docker-compose.local.yaml"
readonly DEFAULT_ENV_FILE=".infrastructure/.local.env"
readonly LOG_DIR="logs"

MODE="dry-run"            # mặc định an toàn: chỉ dry-run
ENV_FILE="$DEFAULT_ENV_FILE"
EXTRA_ARGS=()

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
if [[ -t 1 ]]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'; C_RESET=$'\033[0m'
else
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_RESET=""
fi

info() { echo "${C_BLUE}[INFO]${C_RESET}  $*"; }
ok()   { echo "${C_GREEN}[OK]${C_RESET}    $*"; }
warn() { echo "${C_YELLOW}[WARN]${C_RESET}  $*"; }
die()  { echo "${C_RED}[ERROR]${C_RESET} $*" >&2; exit 1; }

usage() {
  cat <<EOF
Sử dụng: $(basename "$0") [OPTIONS] [-- EXTRA_BUILD_ARGS]

Build ${COMPOSE_FILE}.

OPTIONS:
  -d, --dry-run            Chỉ kiểm tra môi trường + validate cấu hình, KHÔNG build (mặc định)
  -b, --build              Build thật
  -e, --env-file <path>    File .env dùng cho compose (mặc định: ${DEFAULT_ENV_FILE})
  -h, --help               Hiển thị trợ giúp

Mọi argument sau "--" sẽ được truyền thẳng cho "compose build".
Ví dụ: $(basename "$0") --build -- --no-cache --pull
EOF
}

# ----------------------------------------------------------------------------
# Parse arguments
# ----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--dry-run) MODE="dry-run"; shift ;;
    -b|--build)   MODE="build";   shift ;;
    -e|--env-file)
      [[ $# -ge 2 && -n "${2:-}" ]] || die "Thiếu giá trị cho $1"
      ENV_FILE="$2"; shift 2 ;;
    --env-file=*) ENV_FILE="${1#*=}"; shift ;;
    -h|--help)    usage; exit 0 ;;
    --)           shift; EXTRA_ARGS=("$@"); break ;;
    *)            usage >&2; die "Argument không hợp lệ: $1" ;;
  esac
done

# ----------------------------------------------------------------------------
# 1. Kiểm tra Docker & Docker Compose
# ----------------------------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "Chưa cài Docker. Xem: https://docs.docker.com/get-docker/"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)          # Compose v2 (plugin)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)          # Compose v1 (standalone)
  warn "Đang dùng docker-compose v1 (đã lỗi thời), nên nâng cấp lên Compose v2."
else
  die "Không tìm thấy Docker Compose (cả 'docker compose' lẫn 'docker-compose')."
fi

info "Docker version  : $(docker --version)"
info "Compose version : $("${COMPOSE[@]}" version | head -n 1)"

# ----------------------------------------------------------------------------
# 2. Kiểm tra file đầu vào
# ----------------------------------------------------------------------------
[[ -f "$COMPOSE_FILE" ]] || die "Không tìm thấy compose file: ${SCRIPT_DIR}/${COMPOSE_FILE}"
[[ -f "$ENV_FILE"     ]] || die "Không tìm thấy env file: ${ENV_FILE}"

info "Chế độ          : ${MODE}"
info "Compose file    : ${COMPOSE_FILE}"
info "Env file        : ${ENV_FILE}"

COMPOSE_BASE=("${COMPOSE[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
BUILD_CMD=("${COMPOSE_BASE[@]}" build ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"})

# ----------------------------------------------------------------------------
# 3. Validate cấu hình compose (thay biến từ env file, kiểm tra cú pháp YAML)
# ----------------------------------------------------------------------------
info "Đang validate cấu hình compose..."
if ! "${COMPOSE_BASE[@]}" config --quiet; then
  die "Cấu hình compose không hợp lệ. Kiểm tra lại ${COMPOSE_FILE} và ${ENV_FILE}."
fi
ok "Cấu hình compose hợp lệ."

# ----------------------------------------------------------------------------
# 4. Dry-run: dừng tại đây
# ----------------------------------------------------------------------------
if [[ "$MODE" == "dry-run" ]]; then
  info "Các service sẽ được xử lý:"
  "${COMPOSE_BASE[@]}" config --services | sed 's/^/    - /'
  info "Lệnh sẽ chạy khi build thật:"
  printf '    '; printf '%q ' "${BUILD_CMD[@]}"; echo
  ok "DRY-RUN hoàn tất, không có image nào được build."
  exit 0
fi

# ----------------------------------------------------------------------------
# 5. Build thật
# ----------------------------------------------------------------------------
docker info >/dev/null 2>&1 || die "Docker daemon chưa chạy hoặc bạn không có quyền truy cập."

mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/compose-build-$(date +%Y%m%d-%H%M%S).log"

info "Đang build... (log: ${LOG_FILE})"
SECONDS=0

if "${BUILD_CMD[@]}" >"$LOG_FILE" 2>&1; then
  ok "BUILD THÀNH CÔNG sau ${SECONDS}s."
  echo
  echo "================= BUILD LOG ================="
  cat "$LOG_FILE"
  echo "============================================="
  info "Log đã lưu tại: ${SCRIPT_DIR}/${LOG_FILE}"
else
  rc=$?
  echo
  echo "${C_RED}[ERROR]${C_RESET} BUILD THẤT BẠI (exit code ${rc}) sau ${SECONDS}s. 50 dòng log cuối:" >&2
  echo "--------------------------------------------" >&2
  tail -n 50 "$LOG_FILE" >&2
  echo "--------------------------------------------" >&2
  info "Xem log đầy đủ tại: ${SCRIPT_DIR}/${LOG_FILE}" >&2
  exit "$rc"
fi