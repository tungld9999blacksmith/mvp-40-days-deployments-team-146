# syntax=docker/dockerfile:1.7

# ==============================================================================
# Multi-stage image for mock-ev-system (uv workspace member).
#
# The build context is the WORKSPACE ROOT (backend/), because this package
# depends on the workspace lockfile (uv.lock) and the shared `ev-contracts`
# package. Build it from backend/ like this:
#
#     docker build -f mock-ev-system/Dockerfile -t mock-ev-system .
#     docker run --rm -p 8100:8100 mock-ev-system
#
# Optimizations:
#   - uv slim image (Python + uv) only in the builder; runtime is python-slim.
#   - Layer caching: dependencies are installed from pyproject/uv.lock only
#     (bind mounts), so that layer is rebuilt only when a dependency changes,
#     never on a source-code change.
#   - Cache mount: uv's download/wheel cache persists across builds, so even a
#     dependency change only fetches the packages that actually changed.
#   - --no-editable installs the packages as wheels into /app/.venv, so the
#     final stage copies just the venv — no source tree, no uv, no build tools.
# ==============================================================================

ARG PYTHON_VERSION=3.13

# ---- Stage 1: builder (uv slim: Python + uv, nothing else) -------------------
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS builder

# Bytecode-compile for faster cold start; copy (not hardlink) out of the cache
# mount so the venv is self-contained; never download a Python interpreter.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 1) Dependency layer — third-party deps only. The manifests are bind-mounted
#    (not COPY'd), so the layer's cache key is just their content.
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=mock-ev-system/pyproject.toml,target=mock-ev-system/pyproject.toml \
    --mount=type=bind,source=shared/ev-contracts/pyproject.toml,target=shared/ev-contracts/pyproject.toml \
    uv sync --frozen --no-dev --no-install-workspace --package mock-ev-system

# 2) Project layer — bring in the source and install the package (and its
#    workspace dependency ev-contracts) as non-editable wheels into /app/.venv.
COPY pyproject.toml uv.lock ./
COPY shared/ shared/
COPY mock-ev-system/ mock-ev-system/

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev --no-editable --package mock-ev-system


# ---- Stage 2: runtime (slim, no uv, no build tools) --------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# Run as an unprivileged user.
RUN groupadd --system app && useradd --system --gid app --uid 1000 app

# Mount point for a persistent SQLite file (MOCK_DB_PATH=/app/data/mock-ev.db).
# Owned by `app` so a fresh named volume mounted here inherits the ownership.
RUN mkdir -p /app/data && chown app:app /app/data

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy only the built virtual environment from the builder.
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Shared seed data: the mock loads this SQLite dump at startup instead of the
# built-in seed. Regenerate with `tools/ev_mock_data/ev_mock_data.py dump
# --out backend/mock-ev-system/seed-data/ev-mock-dump.sql`. Run with
# -e MOCK_SEED_DUMP= (empty) to use the built-in seed instead.
COPY --chown=app:app mock-ev-system/seed-data/ev-mock-dump.sql /app/seed-data/ev-mock-dump.sql
ENV MOCK_SEED_DUMP=/app/seed-data/ev-mock-dump.sql

USER app

EXPOSE 8100

# In-image healthcheck (no curl in slim) — hits the app's /health route.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "mock_ev_system.main:app", "--host", "0.0.0.0", "--port", "8100"]
