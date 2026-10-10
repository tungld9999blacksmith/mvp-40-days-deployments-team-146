"""Lifecycle-owned async LangGraph persistence, using the application DB config."""

import asyncio
from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.engine import make_url

from src.config import Settings

_active = None
_offline = MemorySaver()


def selector_loop_factory():
    """Uvicorn loop factory for psycopg async on Windows (also works on Unix)."""
    return asyncio.SelectorEventLoop()


def current_checkpointer():
    return _active if _active is not None else _offline


def postgres_dsn(settings: Settings) -> str:
    url = make_url(settings.sqlalchemy_database_url)
    if url.get_backend_name() not in {"postgresql", "postgres"}:
        raise ValueError("PostgreSQL is required for persistent agent checkpoints")
    url = url.set(drivername="postgresql")
    return url.update_query_dict({"connect_timeout": str(settings.database_connect_timeout_seconds)}).render_as_string(
        hide_password=False
    )


@asynccontextmanager
async def checkpoint_lifespan(settings: Settings):
    global _active
    from .dependency import get_agent_graph, get_agent_orchestrator

    get_agent_graph.cache_clear()
    get_agent_orchestrator.cache_clear()
    postgres = settings.agent_checkpoint_mode == "postgres" or (
        settings.agent_checkpoint_mode == "auto"
        and not settings.sqlalchemy_database_url.startswith("sqlite")
        and settings.app_env != "test"
    )
    try:
        if postgres:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg.rows import dict_row
            from psycopg_pool import AsyncConnectionPool

            # The Supabase pooler drops idle connections. Without these, a turn picked a dead
            # one: the query failed or hung, and the conversation stayed locked (409).
            async with AsyncConnectionPool(
                postgres_dsn(settings),
                open=False,
                min_size=0,
                max_size=4,
                timeout=settings.database_connect_timeout_seconds,
                check=AsyncConnectionPool.check_connection,  # discard a dead connection before use
                max_idle=120,
                max_lifetime=900,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": None,
                    "row_factory": dict_row,
                    # Detect a silently dropped peer instead of waiting on it forever.
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 3,
                },
            ) as pool:
                saver = AsyncPostgresSaver(pool)
                await saver.setup()
                _active = saver
                yield saver
        else:
            _active = MemorySaver()
            yield _active
    finally:
        _active = None
        get_agent_graph.cache_clear()
        get_agent_orchestrator.cache_clear()
