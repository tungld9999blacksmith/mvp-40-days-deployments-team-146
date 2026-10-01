# syntax=docker/dockerfile:1.7

# ==============================================================================
# Multi-stage image for the EV Care core backend (uv workspace root, backend/).
#
# The build context is the REPO ROOT (see docker-compose*.yml):
#
#     docker build -f dockerfiles/Dockerfile -t p146-backend .
#
# Optimizations:
#   - uv slim image (Python + uv) only in the builder; runtime is python-slim.
#   - Layer caching: dependencies are installed from pyproject/uv.lock only
#     (bind mounts), so that layer is rebuilt only when a dependency changes,
#     never on a source-code change.
#   - Cache mount: uv's download/wheel cache persists across builds, so even a
#     dependency change only fetches the packages that actually changed.
#   - Runtime gets just the venv + src/: no uv, no build tools, no dev deps.
# ==============================================================================

ARG PYTHON_VERSION=3.11

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
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/mock-ev-system/pyproject.toml,target=mock-ev-system/pyproject.toml \
    --mount=type=bind,source=backend/shared/ev-contracts/pyproject.toml,target=shared/ev-contracts/pyproject.toml \
    uv sync --frozen --no-dev --no-install-workspace

# 2) Workspace layer — install the shared libraries (ev-contracts) as
#    non-editable wheels. The root project is `package = false`, so its own
#    code is not installed; src/ is copied into the runtime stage instead.
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/mock-ev-system/pyproject.toml mock-ev-system/pyproject.toml
COPY backend/shared/ shared/

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev --no-editable


# ---- Stage 2: runtime (slim, no uv, no build tools) --------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# Run as an unprivileged user.
RUN groupadd --system app && useradd --system --gid app --uid 1000 --create-home app

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Venv first (changes rarely), then source (changes often) — so a code change
# only rebuilds the last, small layer.
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Preserve the "src" package layout used by relative imports
# (main.py is loaded as `src.main`, not a top-level module).
COPY --chown=app:app backend/src ./src

# Data directory (mounted as a volume in compose).
RUN mkdir -p /app/data && chown app:app /app/data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status == 200 else 1)"]

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
