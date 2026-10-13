"""LangChain hooks for the Grafana side of agent tracing.

LangChain already reports every model and tool call to LangSmith. These hooks add
the thin OpenTelemetry view of the same calls:

- ``agent_callbacks()`` — one ``chat <model>`` span per chat-model call (model,
  provider, graph node, token counts) plus the latency / token / cost metrics.
- ``instrument_tools(tools)`` — an ``execute_tool <name>`` span around each tool
  body (current while it runs, so DB / HTTP spans nest under it) and the
  ``evcare.agent.tool.calls`` counter / ``evcare.agent.tool.duration`` histogram.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from collections.abc import Callable, Iterable
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from .llm_usage import record_llm_call
from .metrics import get_agent_metrics
from .switch import agent_telemetry_enabled
from .tracing import get_tracer, step

logger = logging.getLogger(__name__)

# ids of tools already wrapped (pydantic tools take no extra attributes, nor hashing).
_traced_tools: set[int] = set()


class OtelLLMCallbackHandler(BaseCallbackHandler):
    """Chat-model calls as OTel spans (parent: the span current at the call)."""

    # Run in the caller's task: the parent span comes from its context.
    run_inline = True
    raise_error = False

    def __init__(self) -> None:
        self._spans: dict[UUID, Span] = {}
        # run_id -> (start, model, node) for the latency / token / cost metrics
        self._calls: dict[UUID, tuple[float, str, str | None]] = {}

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        metadata = metadata or {}
        model = metadata.get("ls_model_name") or "unknown"
        attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.system": metadata.get("ls_provider"),
            "gen_ai.request.model": model,
            "agent.node": metadata.get("langgraph_node"),
        }
        self._calls[run_id] = (time.monotonic(), model, metadata.get("langgraph_node"))
        self._spans[run_id] = get_tracer().start_span(
            f"chat {model}",
            kind=trace.SpanKind.CLIENT,
            attributes={k: v for k, v in attributes.items() if v},
        )

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._spans.pop(run_id, None)
        started, model, node = self._calls.pop(run_id, (time.monotonic(), "unknown", None))
        input_tokens, output_tokens = token_usage(response)
        record_llm_call(
            model=model,
            node=node,
            duration_s=time.monotonic() - started,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if span is None:
            return
        response_model = (getattr(response, "llm_output", None) or {}).get("model_name")
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        if input_tokens or output_tokens:
            span.set_attributes(
                {"gen_ai.usage.input_tokens": input_tokens, "gen_ai.usage.output_tokens": output_tokens}
            )
        span.end()

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        span = self._spans.pop(run_id, None)
        started, model, node = self._calls.pop(run_id, (time.monotonic(), "unknown", None))
        record_llm_call(model=model, node=node, duration_s=time.monotonic() - started, status="error")
        if span is None:
            return
        span.record_exception(error)
        span.set_attribute("error.type", type(error).__name__)
        span.set_status(Status(StatusCode.ERROR, type(error).__name__))
        span.end()


def token_usage(response: Any) -> tuple[int, int]:
    """``(input, output)`` tokens of a LangChain ``LLMResult``; ``(0, 0)`` when the model reports none."""
    for generations in getattr(response, "generations", None) or []:
        for generation in generations:
            usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
            if usage:
                return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    legacy = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
    return int(legacy.get("prompt_tokens") or 0), int(legacy.get("completion_tokens") or 0)


def agent_callbacks() -> list[BaseCallbackHandler]:
    """Callbacks for one agent run (fresh handler: span bookkeeping is per run); none when off."""
    return [OtelLLMCallbackHandler()] if agent_telemetry_enabled() else []


def tool_status(result: Any) -> str:
    """``ok`` / ``empty`` / ``error`` from what a tool returned (ToolResult, dict, JSON, tuple)."""
    if isinstance(result, tuple) and result:  # response_format="content_and_artifact"
        result = result[0]
    status = getattr(result, "status", None)
    if status is None and isinstance(result, dict):
        status = result.get("status")
    if status is None and isinstance(result, str) and result.lstrip().startswith("{"):
        try:
            parsed = json.loads(result)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            status = parsed.get("status")
    return status if status in {"ok", "empty", "error"} else "ok"


def _record(tool_name: str, status: str, current: Any, started: float) -> None:
    current.set(**{"tool.status": status})
    if status == "error":
        current.fail("tool returned error")
        logger.warning("Agent tool %s returned an error result", tool_name)
    _count(tool_name, status, started)


def _count(tool_name: str, status: str, started: float) -> None:
    labels = {"gen_ai.tool.name": tool_name, "tool.status": status}
    metrics = get_agent_metrics()
    metrics.tool_calls.add(1, labels)
    metrics.tool_duration.record(time.monotonic() - started, labels)


def _wrap(tool_name: str, fn: Callable) -> Callable:
    attributes = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool_name}

    if asyncio.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            with step(f"execute_tool {tool_name}", attributes=attributes, langsmith_run=False) as current:
                try:
                    result = await fn(*args, **kwargs)
                except Exception:
                    _count(tool_name, "exception", started)
                    raise
                _record(tool_name, tool_status(result), current, started)
                return result

        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        with step(f"execute_tool {tool_name}", attributes=attributes, langsmith_run=False) as current:
            try:
                result = fn(*args, **kwargs)
            except Exception:
                _count(tool_name, "exception", started)
                raise
            _record(tool_name, tool_status(result), current, started)
            return result

    return sync_wrapper


def instrument_tools(tools: Iterable[Any]) -> list[Any]:
    """Wrap the body of each LangChain tool in place (idempotent); returns the tools.

    Wraps ``func`` / ``coroutine`` of StructuredTool-like objects; ``functools.wraps``
    keeps the signature LangChain inspects for injected ``config`` arguments.
    """
    tools = list(tools)
    for tool in tools:
        if id(tool) in _traced_tools:
            continue
        name = getattr(tool, "name", type(tool).__name__)
        for attr in ("func", "coroutine"):
            fn = getattr(tool, attr, None)
            if callable(fn):
                # Bypass pydantic validation: the field keeps the same callable type.
                object.__setattr__(tool, attr, _wrap(name, fn))
        _traced_tools.add(id(tool))
    return tools
