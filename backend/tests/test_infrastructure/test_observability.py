"""OpenTelemetry setup, log / trace correlation, OTLP log redaction and LangSmith switch."""

import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.config import Settings
from src.infrastructure.fastapi.middlewares import AuditLogMiddleware, CorrelationIdMiddleware, get_trace_id
from src.infrastructure.logging import configure_logging, get_logger
from src.infrastructure.observability import (
    build_telemetry,
    configure_langsmith,
    current_trace_ids,
    instrument_fastapi,
    is_enabled,
    setup_telemetry,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
EMAIL = "nguyen.van.a@example.com"


def _settings(**overrides) -> Settings:
    # _env_file=None: the root .env must not leak into these assertions.
    return Settings(_env_file=None, **overrides)


@pytest.fixture
def telemetry():
    spans, logs = InMemorySpanExporter(), InMemoryLogRecordExporter()
    t = build_telemetry(
        "ev-care-test",
        _settings(app_env="development", otel_enabled=True),
        span_exporter=spans,
        metric_reader=InMemoryMetricReader(),
        log_exporter=logs,
    )
    yield t, spans, logs
    t.shutdown()


@pytest.fixture
def log_output(telemetry):
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    buf = io.StringIO()
    configure_logging(level="INFO", json_logs=True, stream=buf, otel_logger_provider=telemetry[0].logger_provider)
    yield buf
    root.handlers, root.level = saved_handlers, saved_level
    structlog.reset_defaults()


def _app(telemetry) -> FastAPI:
    app = FastAPI()

    @app.get("/echo")
    async def echo():
        get_logger("app.test").info("echo handled")
        return {"trace_id": get_trace_id(), "otel": current_trace_ids()}

    @app.get("/pii")
    async def pii():
        logging.getLogger("app.test").info("contact %s", EMAIL, extra={"email": EMAIL})
        try:
            raise ValueError(f"no owner for {EMAIL}")
        except ValueError:
            logging.getLogger("app.test").exception("lookup failed")
        return {}

    @app.get("/health")
    async def health():
        return {"ok": True}

    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    instrument_fastapi(app, telemetry)
    return app


def _flush(telemetry) -> None:
    telemetry.tracer_provider.force_flush()
    telemetry.logger_provider.force_flush()


# ── enable switch ───────────────────────────────────────────────────────


def test_disabled_by_default():
    settings = _settings(app_env="development")
    assert settings.otel_enabled is False
    assert setup_telemetry("ev-care-test", settings) is None


def test_never_enabled_under_test_env():
    settings = _settings(app_env="test", otel_enabled=True)
    assert is_enabled(settings) is False
    assert setup_telemetry("ev-care-test", settings) is None


def test_no_span_means_no_trace_ids():
    assert current_trace_ids() is None


# ── traces ──────────────────────────────────────────────────────────────


def test_request_creates_server_span_with_route(telemetry, log_output):
    t, spans, _ = telemetry
    TestClient(_app(t)).get("/echo")
    _flush(t)
    server = [s for s in spans.get_finished_spans() if s.kind.name == "SERVER"]
    assert [s.attributes.get("http.route") for s in server] == ["/echo"]
    assert server[0].resource.attributes["service.name"] == "ev-care-test"


def test_health_is_not_traced(telemetry, log_output):
    t, spans, _ = telemetry
    TestClient(_app(t)).get("/health")
    _flush(t)
    assert spans.get_finished_spans() == ()


def test_middleware_and_logs_use_the_span_trace_id(telemetry, log_output):
    t, spans, _ = telemetry
    body = TestClient(_app(t)).get("/echo").json()
    _flush(t)
    [server] = [s for s in spans.get_finished_spans() if s.kind.name == "SERVER"]
    trace_id = format(server.context.trace_id, "032x")
    assert body["trace_id"] == trace_id == body["otel"][0]
    lines = [json.loads(line) for line in log_output.getvalue().splitlines()]
    assert {r["trace_id"] for r in lines if r.get("event") == "echo handled"} == {trace_id}


def test_incoming_traceparent_continues_the_trace(telemetry, log_output):
    t, spans, _ = telemetry
    upstream = "4bf92f3577b34da6a3ce929d0e0e4736"
    body = TestClient(_app(t)).get("/echo", headers={"traceparent": f"00-{upstream}-00f067aa0ba902b7-01"}).json()
    assert body["trace_id"] == upstream


# ── logs over OTLP ──────────────────────────────────────────────────────


def test_logs_are_exported_with_trace_context(telemetry, log_output):
    t, spans, logs = telemetry
    TestClient(_app(t)).get("/echo")
    _flush(t)
    [server] = [s for s in spans.get_finished_spans() if s.kind.name == "SERVER"]
    [record] = [r.log_record for r in logs.get_finished_logs() if "echo handled" in str(r.log_record.body)]
    assert record.trace_id == server.context.trace_id
    assert json.loads(record.body)["trace_id"] == format(server.context.trace_id, "032x")


def test_exported_logs_are_redacted(telemetry, log_output):
    t, _, logs = telemetry
    TestClient(_app(t)).get("/pii")
    _flush(t)
    exported = [
        r.log_record for r in logs.get_finished_logs() if r.log_record.attributes.get("logger.name") == "app.test"
    ]
    assert len(exported) == 2
    for record in exported:
        assert EMAIL not in str(record.body)
        assert EMAIL not in json.dumps(dict(record.attributes))
        assert "exception.message" not in record.attributes
    assert exported[1].attributes["exception.type"] == "ValueError"


# ── LangSmith ───────────────────────────────────────────────────────────


@pytest.fixture
def clean_langsmith_env(monkeypatch):
    from langsmith import run_trees

    for prefix in ("LANGSMITH_", "LANGCHAIN_"):
        for name in ("TRACING_V2", "TRACING", "API_KEY", "ENDPOINT", "PROJECT", "WORKSPACE_ID"):
            monkeypatch.delenv(prefix + name, raising=False)
    # configure_langsmith installs a process-wide client: restore it afterwards.
    monkeypatch.setattr(run_trees, "_CLIENT", None)


def test_langsmith_exports_settings(clean_langsmith_env):
    settings = _settings(
        app_env="development",
        langchain_tracing_v2=True,
        langchain_api_key="lsv2_sk_test",
        langchain_endpoint="https://apac.api.smith.langchain.com",
        langchain_project="evcare-dev",
        langchain_workspace_id="ws-1",
    )
    assert configure_langsmith(settings) is True
    assert os.environ["LANGCHAIN_TRACING_V2"] == os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://apac.api.smith.langchain.com"
    assert os.environ["LANGCHAIN_WORKSPACE_ID"] == "ws-1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_env": "test", "langchain_tracing_v2": True, "langchain_api_key": "k"},
        {"app_env": "development", "langchain_tracing_v2": True, "langchain_api_key": ""},
        {"app_env": "development", "langchain_tracing_v2": False, "langchain_api_key": "k"},
    ],
)
def test_langsmith_off_without_key_or_under_test(clean_langsmith_env, overrides):
    assert configure_langsmith(_settings(**overrides)) is False
    assert os.environ["LANGCHAIN_TRACING_V2"] == os.environ["LANGSMITH_TRACING"] == "false"


def test_agent_import_no_longer_forces_tracing_off():
    """Regression: orchestrator.py set LANGCHAIN_TRACING_V2=false at import, so LangSmith never traced."""
    env = {**os.environ, "APP_ENV": "test", "OPENAI_API_KEY": "test-key", "LANGCHAIN_TRACING_V2": "true"}
    code = "import os, src.agents.orchestrator; print(os.environ['LANGCHAIN_TRACING_V2'])"
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "true"


# ── Celery worker ───────────────────────────────────────────────────────


def test_prefork_detection():
    from celery.concurrency.prefork import TaskPool as PreforkPool
    from celery.concurrency.solo import TaskPool as SoloPool

    from src.celery_tasks import is_prefork_pool

    assert is_prefork_pool(PreforkPool) is True
    assert is_prefork_pool("prefork") is True
    assert is_prefork_pool(SoloPool) is False
    assert is_prefork_pool("solo") is False
    assert is_prefork_pool(None) is False


def test_worker_logs_are_json(monkeypatch, capsys):
    import src.celery_tasks as celery_tasks

    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    monkeypatch.setattr(celery_tasks, "get_settings", lambda: _settings(app_env="test", log_file_formats=""))
    try:
        celery_tasks.configure_worker_logging()
        logging.getLogger("worker.test").info("task done %s", EMAIL)
        [line] = [json.loads(x) for x in capsys.readouterr().out.splitlines() if "task done" in x]
        assert line["logger"] == "worker.test"
        assert EMAIL not in line["event"]
    finally:
        root.handlers, root.level = saved_handlers, saved_level
        structlog.reset_defaults()
