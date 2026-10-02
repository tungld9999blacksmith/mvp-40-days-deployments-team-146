"""Health module — dependency probes.

Each probe runs with its own timeout and all probes run concurrently, so one
hung dependency cannot stall the whole response. Blocking clients (Qdrant
HTTP client, SQLAlchemy engine) run in a worker thread.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from sqlalchemy import text

from src.infrastructure.qdrant.dependency import get_qdrant_service
from src.infrastructure.redis import get_redis_toolkit
from src.infrastructure.supabase.db import engine

from .schemas import DependenciesHealth, DependencyCheck

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS = 3.0


async def _ping_redis() -> str | None:
    if not await get_redis_toolkit().ping():
        raise RuntimeError("PING returned a falsy reply")
    return None


def _ping_qdrant() -> str | None:
    get_qdrant_service().client.get_collections()
    return None


def _ping_database() -> str | None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    # "postgresql" means Supabase; "sqlite" means the local fallback is in use.
    return f"dialect={engine.dialect.name}"


def _describe(exc: BaseException) -> str:
    """Exception type + first line only, so connection strings never leak."""
    if isinstance(exc, TimeoutError):
        return f"timed out after {PROBE_TIMEOUT_SECONDS:g}s"
    first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {first_line[:200]}" if first_line else type(exc).__name__


async def _probe(check: Callable[[], Awaitable[str | None]]) -> DependencyCheck:
    started = time.perf_counter()
    try:
        detail = await asyncio.wait_for(check(), timeout=PROBE_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 — any failure means "down"
        return DependencyCheck(
            status="down",
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            error=_describe(exc),
        )
    return DependencyCheck(
        status="up",
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        detail=detail,
    )


async def check_dependencies() -> DependenciesHealth:
    redis, qdrant, database = await asyncio.gather(
        _probe(_ping_redis),
        _probe(lambda: asyncio.to_thread(_ping_qdrant)),
        _probe(lambda: asyncio.to_thread(_ping_database)),
    )
    checks = {"redis": redis, "qdrant": qdrant, "database": database}
    healthy = all(c.status == "up" for c in checks.values())
    result = DependenciesHealth(status="ok" if healthy else "degraded", checks=checks)
    _log_result(result)
    return result


def _log_result(result: DependenciesHealth) -> None:
    logger.log(
        logging.INFO if result.status == "ok" else logging.WARNING,
        "Dependency check: %s",
        result.status.upper(),
    )
    for name, check in result.checks.items():
        if check.status == "up":
            suffix = f" ({check.detail})" if check.detail else ""
            logger.info("  %-8s UP    %7.1f ms%s", name, check.latency_ms, suffix)
        else:
            logger.warning("  %-8s DOWN  %7.1f ms - %s", name, check.latency_ms, check.error)
