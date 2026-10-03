# =============================================================================
# Root Makefile - dev tools (tools/) + ruff lint / refactor for the backend.
#
# Pass extra arguments with ARGS, e.g.:
#   make api-sync ARGS="list --kind input"
#   make evm ARGS="seed -n 10 --vehicles 1-3 --seed 2026"
#   make railway ARGS="deploy backend"
#   make ruff-check RUFF_PATHS="src/modules"
# =============================================================================

PYTHON     ?= python
ARGS       ?=
BACKEND    := backend
# Paths are relative to backend/ (where ruff.toml lives)
RUFF_PATHS ?= src/ tests/
RUFF       := cd $(BACKEND) && uv run ruff

.DEFAULT_GOAL := help

.PHONY: help \
	api-sync api-sync-config api-sync-list api-sync-check api-sync-sync api-sync-mock \
	evm evm-config evm-seed evm-dump evm-reset \
	repo-sync repo-sync-status repo-sync-dry repo-sync-commit \
	railway railway-check railway-deploy railway-smoke railway-ps \
	ruff-check ruff-fix ruff-format ruff-format-check ruff-refactor ruff-ci ruff-tools

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

# --- api_sync: OpenAPI -> TypeScript + mock JSON ------------------------------
api-sync: ## api_sync with any command: make api-sync ARGS="list --endpoints"
	$(PYTHON) tools/api_sync/api_sync.py $(ARGS)

api-sync-config: ## api_sync: show settings + check the backend is running
	$(PYTHON) tools/api_sync/api_sync.py config $(ARGS)

api-sync-list: ## api_sync: list models
	$(PYTHON) tools/api_sync/api_sync.py list $(ARGS)

api-sync-check: ## api_sync: schema changes since the last sync
	$(PYTHON) tools/api_sync/api_sync.py check $(ARGS)

api-sync-sync: ## api_sync: generate TypeScript + record a sync version
	$(PYTHON) tools/api_sync/api_sync.py sync $(ARGS)

api-sync-mock: ## api_sync: generate JSON sample records
	$(PYTHON) tools/api_sync/api_sync.py mock $(ARGS)

# --- ev_mock_data: data on mock-ev-system ------------------------------------
evm: ## ev_mock_data with any command: make evm ARGS="query vehicles"
	$(PYTHON) tools/ev_mock_data/ev_mock_data.py $(ARGS)

evm-config: ## ev_mock_data: settings, check the mock is up, row counts
	$(PYTHON) tools/ev_mock_data/ev_mock_data.py config $(ARGS)

evm-seed: ## ev_mock_data: generate + import (e.g. ARGS="-n 10 --vehicles 1-3")
	$(PYTHON) tools/ev_mock_data/ev_mock_data.py seed $(ARGS)

evm-dump: ## ev_mock_data: dump the whole mock database to a file
	$(PYTHON) tools/ev_mock_data/ev_mock_data.py dump $(ARGS)

evm-reset: ## ev_mock_data: drop all data and reload the startup data
	$(PYTHON) tools/ev_mock_data/ev_mock_data.py reset $(ARGS)

# --- repo_sync: mirror origin/develop -> deploy repo -------------------------
repo-sync: ## repo_sync: sync (ARGS="--full" to copy everything)
	$(PYTHON) tools/repo_sync/repo_sync.py $(ARGS)

repo-sync-status: ## repo_sync: last synced commit, stale or not
	$(PYTHON) tools/repo_sync/repo_sync.py status

repo-sync-dry: ## repo_sync: show A / M / D files without writing
	$(PYTHON) tools/repo_sync/repo_sync.py --dry-run $(ARGS)

repo-sync-commit: ## repo_sync: sync then git add + commit in the deploy repo
	$(PYTHON) tools/repo_sync/repo_sync.py --commit $(ARGS)

# --- Railway deploy (staging) ------------------------------------------------
railway: ## railway-deploy.sh with any action: make railway ARGS="logs worker"
	bash tools/railway-deploy.sh $(ARGS)

railway-check: ## Railway: CLI/login/link + required variables
	bash tools/railway-deploy.sh check

railway-deploy: ## Railway: check -> up -> smoke (ARGS=app|backend|worker|mock|all)
	bash tools/railway-deploy.sh deploy $(ARGS)

railway-smoke: ## Railway: health checks on the backend domain
	bash tools/railway-deploy.sh smoke

railway-ps: ## Railway (PowerShell script) with any action: ARGS="deploy"
	powershell -ExecutionPolicy Bypass -File tools/railway-deploy.ps1 $(ARGS)

# --- ruff (config: backend/ruff.toml) ----------------------------------------
ruff-check: ## ruff: lint (no changes)
	$(RUFF) check $(RUFF_PATHS)

ruff-fix: ## ruff: lint + apply safe autofixes
	$(RUFF) check --fix $(RUFF_PATHS)

ruff-format: ## ruff: format code
	$(RUFF) format $(RUFF_PATHS)

ruff-format-check: ## ruff: check formatting (no changes)
	$(RUFF) format --check $(RUFF_PATHS)

ruff-refactor: ## ruff: autofix (incl. unsafe fixes, e.g. pyupgrade) + sort imports + format
	$(RUFF) check --fix --unsafe-fixes $(RUFF_PATHS)
	$(RUFF) format $(RUFF_PATHS)

ruff-ci: ruff-check ruff-format-check ## ruff: lint + format check, as in CI

ruff-tools: ## ruff: lint tools/ with the backend config (ARGS="--fix" to fix)
	$(RUFF) check --config ruff.toml ../tools $(ARGS)
