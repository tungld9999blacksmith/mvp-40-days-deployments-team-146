"""CorrelationIdMiddleware + AuditLogMiddleware over the structlog JSON pipeline."""

import io
import json
import logging

import pytest
import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from src.infrastructure.fastapi.middlewares import (
    AuditLogMiddleware,
    CorrelationIdMiddleware,
    get_correlation_id,
    get_trace_id,
)
from src.infrastructure.logging import configure_logging, get_logger

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN_ID = "00f067aa0ba902b7"
TRACEPARENT = f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01"


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/echo")
    async def echo(request: Request):
        request.state.user_id = 42
        logging.getLogger("app.stdlib").info("stdlib line %s", 1)
        get_logger("app.structlog").info("structlog line", extra_field="x")
        return {
            "correlation_id": get_correlation_id(),
            "trace_id": get_trace_id(),
            "state": request.state.correlation_id,
        }

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    @app.get("/stream")
    async def stream():
        async def gen():
            yield b"a"
            yield b"b"

        return StreamingResponse(gen(), media_type="text/plain")

    @app.get("/health")
    async def health():
        return {"ok": True}

    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    return app


@pytest.fixture
def output():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    buf = io.StringIO()
    configure_logging(level="INFO", json_logs=True, stream=buf)
    yield buf
    root.handlers, root.level = saved_handlers, saved_level
    structlog.reset_defaults()


@pytest.fixture
def client(output) -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def _lines(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def _audit(buf: io.StringIO) -> list[dict]:
    return [r for r in _lines(buf) if r.get("logger") == "audit"]


# ── correlation id / trace ──────────────────────────────────────────────


def test_generates_id_when_missing(client):
    resp = client.get("/echo")
    rid = resp.headers["X-Request-ID"]
    assert len(rid) == 32
    assert resp.json() == {"correlation_id": rid, "trace_id": rid, "state": rid}


def test_reuses_incoming_id(client):
    resp = client.get("/echo", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"
    assert resp.json()["correlation_id"] == "abc-123"


def test_accepts_correlation_id_header(client):
    resp = client.get("/echo", headers={"X-Correlation-ID": "corr-1"})
    assert resp.headers["X-Request-ID"] == "corr-1"


@pytest.mark.parametrize("bad", ["a" * 65, "has space", "semi;colon"])
def test_rejects_malformed_id(client, bad):
    resp = client.get("/echo", headers={"X-Request-ID": bad})
    assert resp.headers["X-Request-ID"] != bad


def test_trace_id_from_traceparent(client, output):
    resp = client.get("/echo", headers={"X-Request-ID": "rid-1", "traceparent": TRACEPARENT})
    assert resp.json()["trace_id"] == TRACE_ID
    [rec] = _audit(output)
    assert rec["trace_id"] == TRACE_ID
    assert rec["parent_span_id"] == PARENT_SPAN_ID
    assert rec["correlation_id"] == "rid-1"


@pytest.mark.parametrize("bad", ["garbage", f"00-{'0' * 32}-{PARENT_SPAN_ID}-01"])
def test_invalid_traceparent_falls_back_to_correlation_id(client, bad):
    resp = client.get("/echo", headers={"X-Request-ID": "rid-2", "traceparent": bad})
    assert resp.json()["trace_id"] == "rid-2"


def test_context_is_cleared_after_request(client):
    client.get("/echo")
    assert get_correlation_id() is None
    assert structlog.contextvars.get_contextvars() == {}


def test_app_logs_carry_request_context(client, output):
    client.get("/echo", headers={"X-Request-ID": "rid-3"})
    by_logger = {r["logger"]: r for r in _lines(output)}

    stdlib = by_logger["app.stdlib"]
    assert stdlib["event"] == "stdlib line 1"
    assert stdlib["correlation_id"] == "rid-3"
    assert stdlib["http_path"] == "/echo"
    assert stdlib["level"] == "info"
    assert "timestamp" in stdlib

    native = by_logger["app.structlog"]
    assert native["event"] == "structlog line"
    assert native["extra_field"] == "x"
    assert native["correlation_id"] == "rid-3"


# ── audit log ───────────────────────────────────────────────────────────


def test_audit_record_success(client, output):
    resp = client.get("/echo?x=1", headers={"X-Request-ID": "rid-4", "User-Agent": "ua"})
    [rec] = _audit(output)
    assert rec["event"] == "http_request"
    assert rec["level"] == "info"
    assert rec["correlation_id"] == "rid-4" == resp.headers["X-Request-ID"]
    assert rec["trace_id"] == "rid-4"
    assert rec["http_method"] == "GET"
    assert rec["http_path"] == "/echo"
    assert rec["query"] == "x=1"
    assert rec["status_code"] == 200
    assert rec["user_id"] == 42
    assert rec["user_agent"] == "ua"
    assert rec["duration_ms"] >= 0


def test_audit_levels(client, output):
    client.get("/missing")
    client.get("/boom")
    recs = _audit(output)
    assert [(r["level"], r["status_code"]) for r in recs] == [("warning", 404), ("error", 500)]
    assert recs[1]["error"] == "RuntimeError"


def test_audit_streaming_response(client, output):
    resp = client.get("/stream")
    assert resp.text == "ab"
    assert "X-Request-ID" in resp.headers
    assert _audit(output)[0]["status_code"] == 200


def test_audit_skips_excluded_paths(client, output):
    client.get("/health")
    assert _audit(output) == []


def test_exception_rendered_as_structured_traceback(output):
    try:
        raise ValueError("bad")
    except ValueError:
        logging.getLogger("app.stdlib").exception("failed")
    [rec] = _lines(output)
    assert rec["exception"][0]["exc_type"] == "ValueError"
