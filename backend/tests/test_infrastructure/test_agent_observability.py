"""Agent telemetry: thin OTel spans + metrics (Grafana) and full LangSmith runs, cross-linked.

Grafana side must never carry user content; LangSmith side carries inputs / outputs
(anonymized when LANGCHAIN_REDACT_PII). See docs/observability/OBSERVABILITY_SETUP.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.tools import tool
from langsmith import Client, run_trees
from langsmith.run_helpers import tracing_context
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from src.agents.orchestrator import AgentOrchestrator
from src.agents.telemetry import TurnRecorder, record_tool_call_guard, tool_call_signature
from src.agents.tools.result import ToolResult
from src.config import Settings
from src.infrastructure.llm.base import ChatMessage, LLMProvider, LLMResponse, LLMUsage
from src.infrastructure.llm.traced import TracedLLMProvider, traced
from src.infrastructure.observability import configure_langsmith, instrument_tools, jobs_project, step, tracing
from src.infrastructure.observability import metrics as agent_metrics
from src.infrastructure.observability.agent_hooks import OtelLLMCallbackHandler, tool_status
from src.infrastructure.observability.switch import use_agent_telemetry

EMAIL = "nguyen.van.a@example.com"


# ── fixtures ────────────────────────────────────────────────────────────


class FakeLangSmith(Client):
    """Captures run create / update calls instead of sending them."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(api_key="test", api_url="http://127.0.0.1:9", auto_batch_tracing=False, **kwargs)
        self.captured: dict[str, dict[str, Any]] = {}

    def create_run(self, name, inputs, run_type, **kwargs):
        run_id = str(kwargs["id"])
        self.captured[run_id] = {
            "name": name,
            "run_type": run_type,
            "inputs": inputs,
            "parent_run_id": str(kwargs.get("parent_run_id")) if kwargs.get("parent_run_id") else None,
            "metadata": (kwargs.get("extra") or {}).get("metadata", {}),
            "outputs": kwargs.get("outputs"),
            "error": kwargs.get("error"),
        }

    def update_run(self, run_id, **kwargs):
        run = self.captured.setdefault(str(run_id), {})
        for key in ("outputs", "error"):
            if kwargs.get(key) is not None:
                run[key] = kwargs[key]
        metadata = (kwargs.get("extra") or {}).get("metadata")
        if metadata:
            run.setdefault("metadata", {}).update(metadata)

    def by_name(self, name: str) -> dict[str, Any]:
        matches = [dict(run, id=run_id) for run_id, run in self.captured.items() if run.get("name") == name]
        assert matches, f"no LangSmith run {name!r} in {[r.get('name') for r in self.captured.values()]}"
        return matches[0]


@pytest.fixture
def otel():
    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader])
    tracing.use_tracer_provider(tracer_provider)
    agent_metrics.use_meter_provider(meter_provider)
    use_agent_telemetry(True)
    yield spans, reader
    use_agent_telemetry(None)
    tracing.use_tracer_provider(None)
    agent_metrics.use_meter_provider(None)


@pytest.fixture
def langsmith():
    client = FakeLangSmith()
    with tracing_context(enabled=True, client=client, project_name="test"):
        yield client


def _span(spans: InMemorySpanExporter, name: str):
    found = [s for s in spans.get_finished_spans() if s.name == name]
    assert found, f"no span {name!r} in {[s.name for s in spans.get_finished_spans()]}"
    return found[0]


def _points(reader: InMemoryMetricReader, name: str) -> list[tuple[dict, Any]]:
    data = reader.get_metrics_data()
    points = []
    for resource in data.resource_metrics if data else []:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                if metric.name == name:
                    points += [
                        (dict(p.attributes), getattr(p, "value", None) or p.count) for p in metric.data.data_points
                    ]
    return points


def _all_span_attribute_text(spans: InMemorySpanExporter) -> str:
    return json.dumps([dict(s.attributes) for s in spans.get_finished_spans()], default=str)


# ── step ────────────────────────────────────────────────────────────────


def test_step_cross_links_span_and_langsmith_run(otel, langsmith):
    spans, _ = otel
    with step("unit.work", attributes={"k": "v", "skip": None}, inputs={"message": EMAIL}) as current:
        current.set(**{"result.count": 2})
        current.outputs({"answer": "ok"})

    span = _span(spans, "unit.work")
    run = langsmith.by_name("unit.work")
    assert span.attributes["langsmith.run_id"] == run["id"]
    assert run["metadata"]["otel_trace_id"] == format(span.context.trace_id, "032x")
    assert run["inputs"] == {"message": EMAIL} and run["outputs"] == {"answer": "ok"}
    assert span.attributes["result.count"] == 2 and "skip" not in span.attributes
    assert EMAIL not in _all_span_attribute_text(spans)  # content stays on the LangSmith side


def test_step_marks_both_sides_failed_on_exception(otel, langsmith):
    spans, _ = otel
    with pytest.raises(ValueError), step("unit.boom"):
        raise ValueError("boom")
    assert _span(spans, "unit.boom").status.status_code is StatusCode.ERROR
    assert "boom" in langsmith.by_name("unit.boom")["error"]


def test_step_grafana_only(otel, langsmith):
    spans, _ = otel
    with step("unit.thin", langsmith_run=False):
        pass
    assert _span(spans, "unit.thin")
    assert all(run.get("name") != "unit.thin" for run in langsmith.captured.values())


# ── agent turn ──────────────────────────────────────────────────────────


def _orchestrator(node) -> AgentOrchestrator:
    graph = RunnableLambda(node).with_config(run_name="fake-graph")

    async def no_context(_vehicle_id):
        return {}

    return AgentOrchestrator(graph, no_context)


async def _drain(orchestrator: AgentOrchestrator, message: str) -> list[dict[str, Any]]:
    return [event async for event in orchestrator.run_agent_turn(conversation_id="c-1", user_id=1, message=message)]


def test_turn_is_one_langsmith_trace_and_one_grafana_span(otel, langsmith):
    spans, reader = otel

    async def node(state, config: RunnableConfig):
        return {"response": "Lịch bảo dưỡng mốc 12.000 km."}

    events = asyncio.run(_drain(_orchestrator(node), f"Liên hệ {EMAIL} giúp tôi"))
    assert events[-1]["type"] == "completed"

    turn_span = _span(spans, "agent.turn")
    assert turn_span.attributes["agent.outcome"] == "answered"
    guard_span = _span(spans, "agent.guard.input")
    assert guard_span.parent.span_id == turn_span.context.span_id
    assert guard_span.attributes["guard.decision"] == "flag"
    assert list(guard_span.attributes["guard.pii_types"]) == ["email"]
    assert EMAIL not in _all_span_attribute_text(spans)

    root = langsmith.by_name("agent.turn")
    assert root["parent_run_id"] is None
    assert root["metadata"]["thread_id"] == "c-1"
    assert root["metadata"]["otel_trace_id"] == format(turn_span.context.trace_id, "032x")
    assert root["outputs"]["content"] == "Lịch bảo dưỡng mốc 12.000 km."
    # The input guard and the LangGraph run nest under the turn: one trace per chat turn.
    assert langsmith.by_name("agent.guard.input")["parent_run_id"] == root["id"]
    assert langsmith.by_name("fake-graph")["parent_run_id"] == root["id"]

    assert ({"guard.stage": "input", "guard.decision": "flag", "guard.reason": "pii"}, 1) in _points(
        reader, "evcare.agent.guardrail.decisions"
    )


def test_failed_turn_is_an_error_on_both_sides(otel, langsmith):
    spans, _ = otel

    async def node(state):
        raise RuntimeError("model down")

    events = asyncio.run(_drain(_orchestrator(node), "xin chào"))
    assert events[-1]["message_data"]["content"]  # the user still gets the fallback text

    turn_span = _span(spans, "agent.turn")
    assert turn_span.attributes["agent.outcome"] == "error"
    assert turn_span.attributes["error.type"] == "RuntimeError"
    assert turn_span.status.status_code is StatusCode.ERROR
    assert langsmith.by_name("agent.turn")["error"]


def test_run_config_carries_the_grafana_llm_callback():
    from src.agents.context import AgentCtx
    from src.agents.orchestrator import _run_config

    ctx = AgentCtx(user_id=1, vehicle_id="", conversation_id="c-1")
    use_agent_telemetry(True)
    try:
        config = _run_config(ctx)
        assert any(isinstance(cb, OtelLLMCallbackHandler) for cb in config["callbacks"])
        use_agent_telemetry(False)
        assert not any(isinstance(cb, OtelLLMCallbackHandler) for cb in _run_config(ctx)["callbacks"])
    finally:
        use_agent_telemetry(None)


# ── tools ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (ToolResult(status="error", code="X"), "error"),
        ({"status": "empty"}, "empty"),
        ('{"status": "error", "code": "TIMEOUT"}', "error"),
        (("answer text", {"citations": []}), "ok"),
        ("plain text", "ok"),
    ],
)
def test_tool_status(result, status):
    assert tool_status(result) == status


def test_instrumented_tools_emit_spans_and_metrics(otel):
    spans, reader = otel

    @tool
    async def lookup(plate: str, config: RunnableConfig) -> str:
        """Look up a vehicle."""
        assert config is not None  # injected config still reaches the body
        return '{"status": "error", "code": "NOT_FOUND"}'

    @tool
    def explode(x: int) -> str:
        """Always fails."""
        raise RuntimeError("db down")

    instrument_tools([lookup, explode])
    instrument_tools([lookup])  # idempotent: no double span

    asyncio.run(lookup.ainvoke({"plate": "30A-12345"}))
    with pytest.raises(RuntimeError):
        explode.invoke({"x": 1})

    lookup_spans = [s for s in spans.get_finished_spans() if s.name == "execute_tool lookup"]
    assert len(lookup_spans) == 1
    assert lookup_spans[0].attributes["tool.status"] == "error"
    assert lookup_spans[0].attributes["gen_ai.tool.name"] == "lookup"
    assert "30A-12345" not in _all_span_attribute_text(spans)
    assert _span(spans, "execute_tool explode").status.status_code is StatusCode.ERROR

    calls = _points(reader, "evcare.agent.tool.calls")
    assert ({"gen_ai.tool.name": "lookup", "tool.status": "error"}, 1) in calls
    assert ({"gen_ai.tool.name": "explode", "tool.status": "exception"}, 1) in calls
    durations = _points(reader, "evcare.agent.tool.duration")
    assert {attrs["gen_ai.tool.name"] for attrs, _ in durations} == {"lookup", "explode"}


def test_tool_call_guard_records_modifications(otel):
    spans, reader = otel

    class Response:
        def __init__(self, calls):
            self.tool_calls = calls

    before = tool_call_signature(Response([{"name": "book", "args": {"slot": 1}}]))
    with step("agent.guard.tool_calls", langsmith_run=False) as guard:
        record_tool_call_guard(guard, before, Response([]))
    assert _span(spans, "agent.guard.tool_calls").attributes["guard.decision"] == "modify"
    assert (
        {"guard.stage": "tool_calls", "guard.decision": "modify", "guard.reason": "tool_call_rewrite"},
        1,
    ) in _points(reader, "evcare.agent.guardrail.decisions")


# ── LLM calls ───────────────────────────────────────────────────────────


def test_chat_model_calls_become_thin_spans(otel):
    spans, _ = otel
    model = FakeListChatModel(responses=["xin chào"])
    model.invoke(f"email {EMAIL}", config={"callbacks": [OtelLLMCallbackHandler()]})
    span = [s for s in spans.get_finished_spans() if s.name.startswith("chat ")][0]
    assert span.attributes["gen_ai.operation.name"] == "chat"
    assert EMAIL not in _all_span_attribute_text(spans)


class _StubProvider(LLMProvider):
    def __init__(self) -> None:
        self._model = "stub-model"

    @property
    def provider_name(self) -> str:
        return "stub"

    async def generate_text(self, prompt, config=None):
        return await self.chat([ChatMessage(role="user", content=prompt)], config)

    async def chat(self, messages, config=None):
        return LLMResponse(text="ok", model="stub-model-v1", usage=LLMUsage(input_tokens=12, output_tokens=3))

    async def chat_stream(self, messages, config=None):
        yield "o"
        yield "k"


def test_traced_provider_reports_usage_to_both_backends(otel, langsmith):
    spans, _ = otel
    provider = traced(_StubProvider())
    assert traced(provider) is provider and provider._model == "stub-model"

    response = asyncio.run(provider.chat([ChatMessage(role="user", content=f"email {EMAIL}")]))
    assert response.text == "ok"

    span = _span(spans, "chat stub-model")
    assert span.attributes["gen_ai.system"] == "stub"
    assert span.attributes["gen_ai.response.model"] == "stub-model-v1"
    assert span.attributes["gen_ai.usage.input_tokens"] == 12  # counts only, never text
    assert span.attributes["gen_ai.usage.output_tokens"] == 3
    assert EMAIL not in _all_span_attribute_text(spans)

    run = langsmith.by_name("chat stub-model")
    assert run["run_type"] == "llm"
    assert run["metadata"]["ls_model_name"] == "stub-model"
    assert run["outputs"]["choices"][0]["message"]["content"] == "ok"


def test_traced_provider_forwards_attribute_writes():
    inner = _StubProvider()
    provider = TracedLLMProvider(inner)
    provider._client = "swapped"
    assert inner._client == "swapped"


def _metric_sum(reader: InMemoryMetricReader, name: str, **labels: str) -> float:
    return sum(
        value
        for attrs, value in _points(reader, name)
        if all(attrs.get(k) == v for k, v in labels.items())
    )


def test_llm_call_records_latency_tokens_and_cost(otel):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    from src.infrastructure.observability import TurnUsage, bind_turn_usage

    _, reader = otel
    usage = TurnUsage()
    bind_turn_usage(usage)
    handler = OtelLLMCallbackHandler()
    run_id = uuid.uuid4()
    handler.on_chat_model_start(
        {}, [[]], run_id=run_id, metadata={"ls_model_name": "gpt-4o-mini", "langgraph_node": "agent"}
    )
    message = AIMessage(content="ok", usage_metadata={"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500})
    handler.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=run_id)
    bind_turn_usage(None)

    labels = {"gen_ai.request.model": "gpt-4o-mini", "agent.node": "agent"}
    assert _metric_sum(reader, "evcare.llm.tokens", **labels, **{"gen_ai.token.type": "input"}) == 1000
    assert _metric_sum(reader, "evcare.llm.tokens", **labels, **{"gen_ai.token.type": "output"}) == 500
    expected = (1000 * 0.15 + 500 * 0.60) / 1_000_000
    assert _metric_sum(reader, "evcare.llm.cost.usd", **labels) == pytest.approx(expected)
    assert _metric_sum(reader, "evcare.llm.call.duration", **labels) == 1  # one observation
    assert (usage.llm_calls, usage.input_tokens, usage.output_tokens) == (1, 1000, 500)
    assert usage.cost_usd == pytest.approx(expected)


def test_unpriced_model_counts_tokens_but_not_cost(otel):
    from src.infrastructure.observability import TurnUsage, bind_turn_usage, record_llm_call

    _, reader = otel
    usage = TurnUsage()
    bind_turn_usage(usage)
    assert record_llm_call(model="mystery-model", node="agent", duration_s=0.2, input_tokens=10, output_tokens=5) is None
    bind_turn_usage(None)

    assert _metric_sum(reader, "evcare.llm.tokens", **{"gen_ai.request.model": "mystery-model"}) == 15
    assert _points(reader, "evcare.llm.cost.usd") == []
    assert _metric_sum(reader, "evcare.llm.unpriced.calls") == 1
    assert usage.unpriced_calls == 1 and usage.cost_usd == 0


def test_price_lookup_ignores_provider_prefix_and_case():
    from src.infrastructure.observability.pricing import estimate_cost

    assert estimate_cost("OpenAI/GPT-4o-mini", 1_000_000, 0) == pytest.approx(0.15)
    assert estimate_cost("unknown/model", 10, 10) is None


def test_turn_summary_reports_total_latency_tokens_and_cost(otel):
    from src.infrastructure.observability import record_llm_call

    spans, reader = otel
    recorder = TurnRecorder()
    recorder.bind()
    with step("agent.turn") as current:
        record_llm_call(model="gpt-4o-mini", node="agent", duration_s=0.5, input_tokens=100, output_tokens=20)
        record_llm_call(model="gpt-4o-mini", node="direct", duration_s=0.3, input_tokens=50, output_tokens=10)
        recorder.finish(current)

    attrs = _span(spans, "agent.turn").attributes
    assert attrs["llm.calls"] == 2
    assert attrs["llm.tokens.input"] == 150 and attrs["llm.tokens.output"] == 30
    assert attrs["llm.cost_usd"] == pytest.approx((150 * 0.15 + 30 * 0.60) / 1_000_000)
    assert attrs["llm.duration_ms"] == 800
    assert _metric_sum(reader, "evcare.agent.turn.duration", **{"agent.outcome": "answered"}) == 1
    assert _metric_sum(reader, "evcare.agent.turn.cost.usd") == 1  # one turn observed


def test_agent_telemetry_is_off_by_default(langsmith):
    from src.infrastructure.observability import agent_callbacks, record_llm_call

    assert Settings(_env_file=None).otel_agent_enabled is False

    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    tracing.use_tracer_provider(tracer_provider)
    agent_metrics.use_meter_provider(MeterProvider(metric_readers=[reader]))
    use_agent_telemetry(False)
    try:
        with step("unit.off") as current:
            current.set(k="v")
            current.outputs({"answer": "ok"})
        record_llm_call(model="gpt-4o-mini", node="agent", duration_s=0.1, input_tokens=5, output_tokens=5)
        assert agent_callbacks() == []
    finally:
        use_agent_telemetry(None)
        tracing.use_tracer_provider(None)
        agent_metrics.use_meter_provider(None)

    assert spans.get_finished_spans() == ()
    assert _points(reader, "evcare.llm.tokens") == []
    assert langsmith.by_name("unit.off")["outputs"] == {"answer": "ok"}  # LangSmith keeps tracing


# ── RAG ─────────────────────────────────────────────────────────────────


def _pipeline():
    from src.agents.tools.RAG.query import RAGPipeline
    from src.agents.tools.RAG.query.schemas import QueryAnalysis, RAGResponse, RetrievalCandidate

    candidate = RetrievalCandidate(chunk_id="c1", doc_id="d1", content="Bảo dưỡng mỗi 12.000 km", rerank_score=0.9)

    class Rewriter:
        async def analyze(self, query, vehicle_context=None):
            return QueryAnalysis(original_query=query, rewritten_query=query)

    class Retriever:
        def retrieve(self, analysis, top_candidates):
            return [candidate]

        def select_context(self, candidates, analysis, top_k):
            return candidates

        def expand_neighbors(self, chunks):
            return chunks

    class Reranker:
        def rerank(self, query, candidates, top_k):
            return candidates

    class Citations:
        def build(self, candidates):
            return "context", []

    class Generator:
        async def generate(self, **kwargs):
            return RAGResponse(answer="Mỗi 12.000 km", confidence="high")

    return RAGPipeline(
        rewriter=Rewriter(),
        hybrid_retriever=Retriever(),
        reranker=Reranker(),
        citation_builder=Citations(),
        generator=Generator(),
    )


def test_rag_query_traces_stages_and_counts_outcomes(otel, langsmith):
    spans, reader = otel
    pipeline = _pipeline()
    asyncio.run(pipeline.query("lịch bảo dưỡng", top_k=2))
    asyncio.run(pipeline.query("lịch bảo dưỡng", top_k=2))  # served from cache

    query_spans = [s for s in spans.get_finished_spans() if s.name == "rag.query"]
    assert [s.attributes["rag.cache"] for s in query_spans] == ["miss", "hit"]
    assert query_spans[0].attributes["rag.outcome"] == "answered"
    retrieve = _span(spans, "rag.retrieve")
    assert retrieve.parent.span_id == query_spans[0].context.span_id
    assert retrieve.attributes["rag.hits"] == 1

    docs = langsmith.by_name("rag.retrieve")
    assert docs["run_type"] == "retriever"
    assert docs["outputs"]["documents"][0]["page_content"] == "Bảo dưỡng mỗi 12.000 km"

    queries = _points(reader, "evcare.rag.queries")
    assert ({"rag.outcome": "answered", "rag.cache": "miss"}, 1) in queries
    assert ({"rag.outcome": "answered", "rag.cache": "hit"}, 1) in queries
    stages = {attrs["rag.stage"] for attrs, _ in _points(reader, "evcare.rag.stage.duration")}
    assert stages == {"retrieve", "rerank"}


# ── LangSmith configuration ─────────────────────────────────────────────


@pytest.fixture
def isolated_langsmith(monkeypatch):
    for prefix in ("LANGSMITH_", "LANGCHAIN_"):
        for name in ("TRACING_V2", "TRACING", "API_KEY", "ENDPOINT", "PROJECT", "WORKSPACE_ID"):
            monkeypatch.delenv(prefix + name, raising=False)
    monkeypatch.setattr(run_trees, "_CLIENT", None)


def _ls_settings(**overrides) -> Settings:
    base = {
        "app_env": "development",
        "langchain_tracing_v2": True,
        "langchain_api_key": "lsv2_sk_test",
        "langchain_project": "evcare-staging",
        # Explicit: modules that load_dotenv() at import leak the root .env into os.environ.
        "langchain_jobs_project": "",
        "langchain_redact_pii": False,
    }
    return Settings(_env_file=None, **{**base, **overrides})


def test_redact_pii_installs_an_anonymizing_client(isolated_langsmith):
    configure_langsmith(_ls_settings(langchain_redact_pii=True))
    anonymize = run_trees._CLIENT._anonymizer
    masked = anonymize({"messages": [{"content": f"email {EMAIL} sdt 0912345678"}]})
    text = json.dumps(masked, ensure_ascii=False)
    assert EMAIL not in text and "0912345678" not in text


def test_no_anonymizer_by_default(isolated_langsmith):
    configure_langsmith(_ls_settings())
    assert run_trees._CLIENT._anonymizer is None


def test_worker_traces_into_the_jobs_project(isolated_langsmith):
    settings = _ls_settings()
    assert jobs_project(settings) == "evcare-staging-jobs"
    assert jobs_project(_ls_settings(langchain_jobs_project="custom")) == "custom"
    configure_langsmith(settings, project=jobs_project(settings))
    assert os.environ["LANGSMITH_PROJECT"] == os.environ["LANGCHAIN_PROJECT"] == "evcare-staging-jobs"


def test_streamed_agent_llm_reports_token_usage(monkeypatch):
    """Regression: without stream_usage the streamed chat turn had no tokens / cost in LangSmith."""
    from src.agents import graph

    settings = Settings(
        _env_file=None, app_env="test", llm_provider="openrouter", openrouter_api_key="k", llm_fallback_provider=""
    )
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    assert graph.get_agent_llm().stream_usage is True
