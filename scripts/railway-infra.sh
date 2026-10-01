#!/usr/bin/env bash
# =============================================================================
# railway-infra.sh — deploy/manage dev infra (Redis + mock-ev-system) on
# Railway so the core backend can run locally in a terminal (debug mode).
# See docs/RUN_LOCAL_BACKEND_RAILWAY.md. Requires Railway CLI >= 5.x and a
# prior `railway login`.
#
# Usage:
#   ./scripts/railway-infra.sh init [project-name]   # create project + link
#   ./scripts/railway-infra.sh link                  # link existing project
#   ./scripts/railway-infra.sh setup [secret]        # add Redis + mock service
#   ./scripts/railway-infra.sh deploy                # upload backend/, deploy mock
#   ./scripts/railway-infra.sh domain                # public domain for mock
#   ./scripts/railway-infra.sh webhook <url|"">      # set/clear MOCK_WEBHOOK_URL
#   ./scripts/railway-infra.sh env [slot]            # print .env (repo root) lines
#   ./scripts/railway-infra.sh status | logs
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MOCK_SERVICE="mock-ev-system"
REDIS_SERVICE="Redis"
WEBHOOK_PATH="/api/v1/integrations/oem/webhooks"

info() { printf '\033[36m[INFO]\033[0m  %s\n' "$*"; }
ok()   { printf '\033[32m[OK]\033[0m    %s\n' "$*"; }
warn() { printf '\033[33m[WARN]\033[0m  %s\n' "$*"; }
err()  { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; }

command -v railway >/dev/null 2>&1 || { err "Railway CLI not found. Install: npm i -g @railway/cli"; exit 1; }

PYTHON="$(command -v python3 || command -v python || true)"

backend_env_value() {
  local key="$1" file="$REPO_ROOT/.env"
  [[ -f "$file" ]] || return 0
  grep -E "^\s*${key}\s*=" "$file" | head -n1 | cut -d= -f2- | sed -e "s/^[\"']//" -e "s/[\"']\s*$//" -e 's/\s*$//'
}

action="${1:-status}"
shift || true

case "$action" in
  init)
    name="${1:-p146-dev-infra}"
    info "Creating Railway project '$name' and linking the repo root..."
    railway init --name "$name"
    ok "Linked. Next: ./scripts/railway-infra.sh setup"
    ;;
  link)
    railway link
    ;;
  setup)
    secret="${1:-$(backend_env_value OEM_WEBHOOK_SECRET)}"
    if [[ -z "$secret" || "$secret" == "change-me" ]]; then
      secret="$(openssl rand -hex 32 2>/dev/null || "$PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"
      warn "Generated a new webhook secret. Put it in .env (repo root):"
      echo "  OEM_WEBHOOK_SECRET=$secret"
    fi
    info "Adding Redis database..."
    railway add --database redis
    info "Adding empty service '$MOCK_SERVICE'..."
    railway add --service "$MOCK_SERVICE" \
      --variables "RAILWAY_DOCKERFILE_PATH=mock-ev-system/Dockerfile.railway" \
      --variables "PORT=8100" \
      --variables "MOCK_WEBHOOK_SECRET=$secret" \
      --variables "MOCK_WEBHOOK_USAGE_MIN_INTERVAL_SECONDS=300"
    ok "Done. Next: ./scripts/railway-infra.sh deploy ; then domain"
    ;;
  deploy)
    info "Uploading backend/ and deploying '$MOCK_SERVICE'..."
    railway up ./backend --path-as-root --service "$MOCK_SERVICE" --detach \
      --message "mock-ev-system dev deploy"
    ok "Deploy started. Follow with: ./scripts/railway-infra.sh logs"
    ;;
  domain)
    railway domain --service "$MOCK_SERVICE" --port 8100
    ;;
  webhook)
    [[ $# -ge 1 ]] || { err "Pass the public base URL of your local backend (or \"\" to disable)."; exit 1; }
    if [[ -n "$1" ]]; then
      target="${1%/}${WEBHOOK_PATH}"
      info "Setting MOCK_WEBHOOK_URL=$target (triggers a redeploy)..."
      railway variable set "MOCK_WEBHOOK_URL=$target" --service "$MOCK_SERVICE"
    else
      info "Removing MOCK_WEBHOOK_URL (webhooks disabled, triggers a redeploy)..."
      railway variable delete MOCK_WEBHOOK_URL --service "$MOCK_SERVICE"
    fi
    ok "Done."
    ;;
  env)
    slot="${1:-0}"
    [[ "$slot" =~ ^[0-4]$ ]] || { err "Slot must be 0-4."; exit 1; }
    [[ -n "$PYTHON" ]] || { err "python is required for 'env'."; exit 1; }
    redis_json="$(railway variable list --service "$REDIS_SERVICE" --json)"
    mock_json="$(railway variable list --service "$MOCK_SERVICE" --json)"
    # Slot N uses DBs 3N (broker), 3N+1 (result backend), 3N+2 (app cache).
    REDIS_JSON="$redis_json" MOCK_JSON="$mock_json" SLOT="$slot" "$PYTHON" - <<'PY'
import json, os, sys
from urllib.parse import unquote, urlparse

redis = json.loads(os.environ["REDIS_JSON"])
mock = json.loads(os.environ["MOCK_JSON"])
slot = int(os.environ["SLOT"])

public_url = redis.get("REDIS_PUBLIC_URL")
if not public_url:
    sys.exit("REDIS_PUBLIC_URL is empty. Enable Redis -> Settings -> Networking -> TCP Proxy (port 6379).")
url = urlparse(public_url)
domain = mock.get("RAILWAY_PUBLIC_DOMAIN")
oem_url = f"https://{domain}" if domain else "<run: ./scripts/railway-infra.sh domain>"
broker_db = 3 * slot

print(f"# Paste these into .env (repo root) (slot {slot}):")
print(f"OEM_API_BASE_URL={oem_url}")
print(f"OEM_WEBHOOK_SECRET={mock.get('MOCK_WEBHOOK_SECRET', '')}")
print("REDIS_URL=")
print(f"REDIS_HOST={url.hostname}")
print(f"REDIS_PORT={url.port}")
print(f"REDIS_PASSWORD='{unquote(url.password or '')}'")
print(f"REDIS_DB={broker_db + 2}")
print(f"CELERY_BROKER_DB={broker_db}")
print(f"CELERY_BACKEND_DB={broker_db + 1}")
print(f"REDIS_KEY_PREFIX=p146-dev{slot}")
print("REDIS_BROKER_URL=")
print("REDIS_BACKEND_URL=")
PY
    ;;
  status)
    railway status
    echo
    railway deployment list --service "$MOCK_SERVICE" --limit 5
    ;;
  logs)
    railway logs --service "$MOCK_SERVICE"
    ;;
  *)
    err "Unknown action: $action"
    exit 1
    ;;
esac
