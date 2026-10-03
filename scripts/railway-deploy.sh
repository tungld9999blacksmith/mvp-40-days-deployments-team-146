#!/usr/bin/env bash
# =============================================================================
# railway-deploy.sh - deploy backend / worker / mock-ev-system to Railway
# (staging) from a local machine - the same steps as the `deploy-backend` +
# `smoke-test` CI jobs. See docs/deployments/RAILWAY_BACKEND_DEPLOYMENT.MD
# (step 9). Requires Railway CLI >= 5.x, python, a prior `railway login` (or
# RAILWAY_API_TOKEN) and the repo root linked (`railway link`).
#
# Usage:
#   ./scripts/railway-deploy.sh check            # CLI/login/link + required variables
#   ./scripts/railway-deploy.sh vars             # push .railway.env + Redis refs to backend/worker (no redeploy)
#   ./scripts/railway-deploy.sh deploy [target]  # check -> railway up -> smoke
#                                                #   target: app (default: backend+worker),
#                                                #   backend, worker, mock, all (mock->backend->worker)
#   ./scripts/railway-deploy.sh smoke            # GET /health + /api/v1/health/dependencies
#   ./scripts/railway-deploy.sh status
#   ./scripts/railway-deploy.sh logs [service]   # default: backend
#
# Env: RAILWAY_ENV (default staging), BACKEND_URL (default: backend public
# domain), SKIP_CHECK=1 (deploy without the variable check).
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENVIRONMENT="${RAILWAY_ENV:-staging}"
BACKEND_SERVICE="backend"
WORKER_SERVICE="worker"
MOCK_SERVICE="mock-ev-system"
REDIS_SERVICE="Redis"
ENV_FILE="infrastructure/backend/railway/.railway.env"

# Redis comes from reference variables (private network), OEM_API_BASE_URL is
# set per service to the mock (step 5b) - never copied from .railway.env.
SKIP_KEYS=" REDIS_URL REDIS_HOST REDIS_PORT REDIS_PASSWORD REDIS_BROKER_URL REDIS_BACKEND_URL OEM_API_BASE_URL "

info() { printf '\033[36m[INFO]\033[0m  %s\n' "$*"; }
ok()   { printf '\033[32m[OK]\033[0m    %s\n' "$*"; }
warn() { printf '\033[33m[WARN]\033[0m  %s\n' "$*"; }
err()  { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; }

command -v railway >/dev/null 2>&1 || { err "Railway CLI not found. Install: npm i -g @railway/cli"; exit 1; }
PYTHON="$(command -v python3 || command -v python || true)"
[[ -n "$PYTHON" ]] || { err "python is required to parse Railway JSON output"; exit 1; }

prerequisites() {
  railway whoami >/dev/null 2>&1 || { err "Not logged in. Run 'railway login' (or set RAILWAY_API_TOKEN)."; exit 1; }
  railway status >/dev/null 2>&1 || { err "Repo root is not linked. Run 'railway link' and pick the project + '$ENVIRONMENT'."; exit 1; }
}

# Prints the resolved variables of a service as JSON.
service_vars() {
  railway variable list --service "$1" --environment "$ENVIRONMENT" --json \
    || { err "Cannot read variables of service '$1' ($ENVIRONMENT)."; exit 1; }
}

# Reads one key from the JSON on stdin (empty when missing).
json_get() {
  "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]) or "")' "$1"
}

# Checks one service; prints the error/warning lines and the error count as
# the last line.
check_service() {
  local name="$1"; shift
  service_vars "$name" | "$PYTHON" -c '
import json, re, sys
name, is_mock, required = sys.argv[1], sys.argv[2] == "1", sys.argv[3:]
v = json.load(sys.stdin)
errors = 0
def e(msg):
    global errors
    errors += 1
    print(f"E {name}: {msg}")
def w(msg):
    print(f"W {name}: {msg}")
for key in required:
    if not v.get(key):
        e(f"missing {key}")
if not is_mock:
    redis = v.get("REDIS_URL") or v.get("REDIS_HOST") or ""
    if not redis or re.search(r"localhost|127\.0\.0\.1", redis):
        e("Redis points to localhost (set REDIS_HOST/PORT/PASSWORD - run vars)")
    if not v.get("DATABASE_URL") and not v.get("DATABASE_PASSWORD"):
        e("no DATABASE_URL / DATABASE_PASSWORD -> app falls back to SQLite")
    if v.get("APP_ENV") != "production":
        e("APP_ENV must be production (is %r)" % v.get("APP_ENV", ""))
    if not v.get("QDRANT_URL"):
        w("no QDRANT_URL -> Qdrant uses local storage inside the container")
    if not v.get("FIREBASE_CREDENTIAL_JSON"):
        w("no FIREBASE_CREDENTIAL_JSON")
    local = [k for k, val in v.items() if "localhost" in str(val) and not k.startswith("REDIS_")]
    if local:
        w("still localhost in: " + ", ".join(sorted(local)))
print(errors)
' "$name" "$([[ "$name" == "$MOCK_SERVICE" ]] && echo 1 || echo 0)" "$@"
}

run_check() {
  prerequisites
  info "Checking variables ($ENVIRONMENT)..."
  local total=0 out line
  for spec in "$BACKEND_SERVICE RAILWAY_DOCKERFILE_PATH PORT" \
              "$WORKER_SERVICE RAILWAY_DOCKERFILE_PATH" \
              "$MOCK_SERVICE RAILWAY_DOCKERFILE_PATH PORT"; do
    # shellcheck disable=SC2086
    out="$(check_service $spec)"
    while IFS= read -r line; do
      case "$line" in
        "E "*) err "${line#E }" ;;
        "W "*) warn "${line#W }" ;;
        *) total=$((total + line)) ;;
      esac
    done <<< "$out"
  done
  if (( total > 0 )); then
    err "$total problem(s). Fix them (./scripts/railway-deploy.sh vars) or set SKIP_CHECK=1."
    exit 1
  fi
  ok "Variables look good."
}

backend_url() {
  if [[ -n "${BACKEND_URL:-}" ]]; then echo "${BACKEND_URL%/}"; return; fi
  local domain
  domain="$(service_vars "$BACKEND_SERVICE" | json_get RAILWAY_PUBLIC_DOMAIN)"
  [[ -n "$domain" ]] || { err "Backend has no public domain. Generate one or set BACKEND_URL."; exit 1; }
  echo "https://$domain"
}

run_smoke() {
  local base body
  base="$(backend_url)"
  info "GET $base/health (waiting for the new deployment)..."
  curl --fail --silent --show-error --retry 10 --retry-delay 10 --retry-all-errors \
    --max-time 15 "$base/health" >/dev/null || { err "/health did not return 200."; exit 1; }
  ok "/health OK"

  info "GET $base/api/v1/health/dependencies"
  # 503 when degraded - the body still has the per-dependency checks.
  body="$(curl --silent --show-error --max-time 20 "$base/api/v1/health/dependencies")"
  printf '%s' "$body" | "$PYTHON" -c '
import json, sys
d = json.load(sys.stdin)
for name, c in d["checks"].items():
    color = "32" if c["status"] == "up" else "31"
    note = c["error"] or c["detail"] or ""
    print("\033[%sm  %-9s %-5s %7s ms  %s\033[0m" % (color, name, c["status"].upper(), c["latencyMs"], note))
if (d["checks"].get("database") or {}).get("detail") == "dialect=sqlite":
    print("[33m[WARN][0m  Database is the SQLite fallback - set DATABASE_* (Supabase) on the service")
sys.exit(0 if d["status"] == "ok" else 1)
' || { err "Dependencies degraded."; exit 1; }
  ok "Dependencies OK"
}

push_vars() {
  prerequisites
  [[ -f "$ENV_FILE" ]] || { err "$ENV_FILE not found. Copy .railway.example.env and fill it in (step 6.1)."; exit 1; }

  # KEY<TAB>VALUE lines: comments/blank lines skipped, one pair of quotes stripped.
  local parsed
  parsed="$("$PYTHON" - "$ENV_FILE" <<'PY'
import re, sys
for raw in open(sys.argv[1], encoding="utf-8"):
    m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$", raw.rstrip("\r\n"))
    if not m or raw.lstrip().startswith("#"):
        continue
    value = m.group(2).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    print(f"{m.group(1)}\t{value}")
PY
)"

  local app_env
  app_env="$(awk -F'\t' '$1=="APP_ENV"{print $2}' <<< "$parsed")"
  if [[ -n "$app_env" && "$app_env" != "production" ]]; then
    err "APP_ENV in $ENV_FILE is '$app_env' - must be 'production' on Railway."
    exit 1
  fi

  local svc key value count
  for svc in "$BACKEND_SERVICE" "$WORKER_SERVICE"; do
    info "Setting variables on '$svc' ($ENVIRONMENT, no redeploy)..."
    count=0
    while IFS=$'\t' read -r key value; do
      [[ -z "$value" || "$SKIP_KEYS" == *" $key "* ]] && continue
      [[ "$value" == *localhost* && "$svc" == "$BACKEND_SERVICE" ]] && warn "$key contains 'localhost' - check it"
      # Value via stdin: secrets stay off the command line, JSON quotes survive.
      printf '%s' "$value" | railway variable set "$key" --stdin --service "$svc" \
        --environment "$ENVIRONMENT" --skip-deploys >/dev/null \
        || { err "Failed to set $key on '$svc'."; exit 1; }
      count=$((count + 1))
    done <<< "$parsed"
    railway variable set --service "$svc" --environment "$ENVIRONMENT" --skip-deploys \
      "REDIS_HOST=\${{${REDIS_SERVICE}.REDISHOST}}" \
      "REDIS_PORT=\${{${REDIS_SERVICE}.REDISPORT}}" \
      "REDIS_PASSWORD=\${{${REDIS_SERVICE}.REDISPASSWORD}}" >/dev/null
    # REDIS_URL wins over REDIS_HOST in config.py - make sure it is gone.
    if [[ -n "$(service_vars "$svc" | json_get REDIS_URL)" ]]; then
      railway variable delete REDIS_URL --service "$svc" --environment "$ENVIRONMENT"
    fi
    ok "'$svc' done ($((count + 3)) variables)."
  done
  ok "Variables pushed. Deploy to apply: ./scripts/railway-deploy.sh deploy"
}

run_deploy() {
  if [[ "${SKIP_CHECK:-0}" == "1" ]]; then prerequisites; else run_check; fi
  local target="${1:-app}" steps commit svc
  case "$target" in
    app)     steps=("$BACKEND_SERVICE" "$WORKER_SERVICE") ;;
    backend) steps=("$BACKEND_SERVICE") ;;
    worker)  steps=("$WORKER_SERVICE") ;;
    mock)    steps=("$MOCK_SERVICE") ;;
    all)     steps=("$MOCK_SERVICE" "$BACKEND_SERVICE" "$WORKER_SERVICE") ;;
    *) err "Unknown target: $target (app | backend | worker | mock | all)"; exit 1 ;;
  esac
  commit="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  for svc in "${steps[@]}"; do
    info "Deploying '$svc' ($ENVIRONMENT)..."
    if [[ "$svc" == "$MOCK_SERVICE" ]]; then
      # Mock is built with backend/ as root (uv workspace).
      railway up ./backend --path-as-root --ci --service "$svc" --environment "$ENVIRONMENT" --message "local deploy $commit"
    else
      railway up --ci --service "$svc" --environment "$ENVIRONMENT" --message "local deploy $commit"
    fi
    ok "'$svc' built and deployed."
  done
  if [[ " ${steps[*]} " == *" $BACKEND_SERVICE "* ]]; then run_smoke; fi
}

ACTION="${1:-check}"
case "$ACTION" in
  check)  run_check ;;
  vars)   push_vars ;;
  deploy) run_deploy "${2:-app}" ;;
  smoke)  prerequisites; run_smoke ;;
  status)
    prerequisites
    railway status
    for svc in "$BACKEND_SERVICE" "$WORKER_SERVICE" "$MOCK_SERVICE"; do
      echo; info "$svc"
      railway deployment list --service "$svc" --environment "$ENVIRONMENT" --limit 3
    done
    ;;
  logs)   railway logs --service "${2:-$BACKEND_SERVICE}" --environment "$ENVIRONMENT" ;;
  *)
    err "Unknown action: $ACTION (check | vars | deploy | smoke | status | logs)"
    exit 1
    ;;
esac
