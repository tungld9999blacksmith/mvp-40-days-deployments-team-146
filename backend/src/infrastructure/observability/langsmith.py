"""LangSmith tracing switch for LangChain / LangGraph runs.

The LangChain SDK reads its settings from ``os.environ`` only, while the app reads
the root ``.env`` through ``Settings``. ``configure_langsmith`` copies the values
over once at start-up, so tracing no longer depends on which module happened to
call ``load_dotenv`` first. Tests never trace (the root ``.env`` leaks into them).

It also installs the process-wide LangSmith client used by both LangChain's tracer
and ``langsmith.trace``: with ``LANGCHAIN_REDACT_PII`` every input / output string is
masked by the log redactor before it leaves the process.
"""

from __future__ import annotations

import os
from typing import Any

from src.config import Settings

_PREFIXES = ("LANGSMITH_", "LANGCHAIN_")


def _set(name: str, value: str) -> None:
    # The SDK checks LANGSMITH_* before LANGCHAIN_*: write both so neither wins stale.
    for prefix in _PREFIXES:
        os.environ[prefix + name] = value


def jobs_project(settings: Settings) -> str:
    """LangSmith project of background jobs: own quota view, chat project stays clean."""
    return settings.langchain_jobs_project or (
        f"{settings.langchain_project}-jobs" if settings.langchain_project else ""
    )


def pii_anonymizer() -> Any:
    """Masks emails / phones (same rules as the logs) in every traced string."""
    from langsmith.anonymizer import create_anonymizer

    from src.infrastructure.logging.pii import redact_text

    return create_anonymizer(lambda value, _path: redact_text(value))


def _install_client(redact_pii: bool) -> None:
    """Replace the cached client so it picks up the env above (+ the anonymizer)."""
    from langsmith import Client, run_trees

    run_trees._CLIENT = Client(anonymizer=pii_anonymizer() if redact_pii else None)


def configure_langsmith(settings: Settings, *, project: str | None = None) -> bool:
    """Export LangSmith settings to the environment; returns whether tracing is on.

    ``project`` overrides ``LANGCHAIN_PROJECT`` for this process (the Celery worker
    passes ``jobs_project``).
    """
    enabled = settings.langchain_tracing_v2 and bool(settings.langchain_api_key) and settings.app_env != "test"
    _set("TRACING_V2", "true" if enabled else "false")
    _set("TRACING", "true" if enabled else "false")
    if enabled:
        for name, value in (
            ("API_KEY", settings.langchain_api_key),
            ("ENDPOINT", settings.langchain_endpoint),
            ("PROJECT", project or settings.langchain_project),
            ("WORKSPACE_ID", settings.langchain_workspace_id),
        ):
            if value:
                _set(name, value)
    try:  # the SDK memoizes env lookups; drop anything read before this point
        from langsmith import utils as ls_utils

        ls_utils.get_env_var.cache_clear()
    except (ImportError, AttributeError):
        pass
    if enabled:
        _install_client(settings.langchain_redact_pii)
    return enabled
