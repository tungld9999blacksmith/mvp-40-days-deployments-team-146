"""On/off switch for the Grafana side of agent telemetry (``OTEL_AGENT_ENABLED``, default off).

Off: no agent spans, no agent metrics, no agent turn log line. LangSmith tracing is
independent of this switch (it follows ``LANGCHAIN_TRACING_V2``) and is never affected.
"""

from __future__ import annotations

from src.config import get_settings

_override: bool | None = None


def use_agent_telemetry(enabled: bool | None) -> None:
    """Force the switch (tests); ``None`` goes back to the setting."""
    global _override
    _override = enabled


def agent_telemetry_enabled() -> bool:
    return _override if _override is not None else get_settings().otel_agent_enabled
