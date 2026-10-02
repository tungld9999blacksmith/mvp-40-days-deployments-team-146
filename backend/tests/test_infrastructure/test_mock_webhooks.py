"""Tests for the mock-ev-system outgoing webhooks (FEAT-VEH-001, Q-310)."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from ev_contracts import (
    WEBHOOK_EVENT_ID_HEADER,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
    WebhookEvent,
    WebhookEventType,
    sign_webhook,
    verify_webhook_signature,
)
from fastapi.testclient import TestClient
from mock_ev_system import webhooks
from mock_ev_system.main import app
from mock_ev_system.routers import maintenance as maintenance_router

SECRET = "test-secret"


class _Receiver:
    """Minimal HTTP server that records requests and answers a fixed status."""

    def __init__(self, status: int = 202) -> None:
        self.status = status
        self.requests: list[tuple[dict[str, str], bytes]] = []
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server API
                length = int(self.headers["Content-Length"])
                # HTTP header names are case-insensitive; urllib sends e.g. "X-oem-timestamp".
                headers = {k.lower(): v for k, v in self.headers.items()}
                receiver.requests.append((headers, self.rfile.read(length)))
                self.send_response(receiver.status)
                self.end_headers()

            def log_message(self, *args):  # silence test output
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/webhook"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def _settings(url: str | None) -> webhooks.WebhookSettings:
    return webhooks.WebhookSettings(url=url, secret=SECRET, usage_min_interval_seconds=300, timeout_seconds=2)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(webhooks, "RETRY_BACKOFF_SECONDS", (0.0, 0.0))


# ── Signature contract ───────────────────────────────────────────────────


def test_signature_roundtrip_and_tamper_detection():
    body = b'{"eventType":"vehicle.usage.updated"}'
    signature = sign_webhook(SECRET, 1727500000, body)

    assert signature.startswith("sha256=")
    assert verify_webhook_signature(SECRET, 1727500000, body, signature)
    assert not verify_webhook_signature(SECRET, 1727500000, body + b" ", signature)
    assert not verify_webhook_signature(SECRET, 1727500001, body, signature)
    assert not verify_webhook_signature("other-secret", 1727500000, body, signature)


def test_build_request_is_signed_and_parsable():
    event_id, headers, body = webhooks.build_request(WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-001", SECRET)

    assert headers[WEBHOOK_EVENT_ID_HEADER] == event_id
    assert verify_webhook_signature(SECRET, headers[WEBHOOK_TIMESTAMP_HEADER], body, headers[WEBHOOK_SIGNATURE_HEADER])
    event = WebhookEvent.model_validate_json(body)
    assert event.event_type is WebhookEventType.VEHICLE_USAGE_UPDATED
    assert event.vehicle_id == "VEH-001"


# ── Delivery ─────────────────────────────────────────────────────────────


def test_send_event_disabled_returns_none():
    result = asyncio.run(webhooks.send_event(WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-001", _settings(None)))
    assert result is None


def test_send_event_delivers_signed_request():
    with _Receiver(status=202) as receiver:
        result = asyncio.run(
            webhooks.send_event(
                WebhookEventType.VEHICLE_SERVICE_HISTORY_UPDATED,
                "VEH-001",
                _settings(receiver.url),
            )
        )

    assert result.delivered and result.status_code == 202 and result.attempts == 1
    headers, body = receiver.requests[0]
    assert verify_webhook_signature(
        SECRET,
        headers[WEBHOOK_TIMESTAMP_HEADER.lower()],
        body,
        headers[WEBHOOK_SIGNATURE_HEADER.lower()],
    )
    assert json.loads(body)["eventType"] == "vehicle.service_history.updated"


def test_send_event_does_not_retry_client_errors():
    with _Receiver(status=401) as receiver:
        result = asyncio.run(
            webhooks.send_event(WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-001", _settings(receiver.url))
        )

    assert not result.delivered
    assert result.attempts == 1
    assert len(receiver.requests) == 1


def test_send_event_retries_server_errors():
    with _Receiver(status=503) as receiver:
        result = asyncio.run(
            webhooks.send_event(WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-001", _settings(receiver.url))
        )

    assert not result.delivered
    assert result.attempts == 3
    assert len(receiver.requests) == 3


def test_usage_events_are_throttled_per_vehicle(monkeypatch):
    sent: list[tuple[WebhookEventType, str]] = []
    monkeypatch.setattr(webhooks, "load_settings", lambda: _settings("http://unused"))
    monkeypatch.setattr(webhooks, "dispatch", lambda event, vid: sent.append((event, vid)))
    webhooks.reset_throttle()

    webhooks.dispatch_usage_updated("VEH-001")
    webhooks.dispatch_usage_updated("VEH-001")
    webhooks.dispatch_usage_updated("VEH-002")

    assert sent == [
        (WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-001"),
        (WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-002"),
    ]
    webhooks.reset_throttle()


# ── Mock API endpoints ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def mock_client():
    with TestClient(app) as client:
        yield client


def test_create_service_record_dispatches_webhook(mock_client, monkeypatch):
    sent: list[tuple[WebhookEventType, str]] = []
    monkeypatch.setattr(maintenance_router, "dispatch", lambda event, vid: sent.append((event, vid)))

    resp = mock_client.post(
        "/vehicles/VEH-001/service-history",
        json={
            "service_center_id": "SC-01",
            "service_date": "2026-09-28",
            "km_at_service": 42_600,
            "items_done": "Kiểm tra phanh",
            "total_cost": 150000,
        },
    )

    assert resp.status_code == 201
    order_id = resp.json()["order_id"]
    history = mock_client.get("/vehicles/VEH-001/service-history").json()
    assert history[0]["order_id"] == order_id
    assert sent == [(WebhookEventType.VEHICLE_SERVICE_HISTORY_UPDATED, "VEH-001")]


def test_create_service_record_unknown_center(mock_client):
    resp = mock_client.post(
        "/vehicles/VEH-001/service-history",
        json={
            "service_center_id": "SC-XX",
            "service_date": "2026-09-28",
            "km_at_service": 1,
            "items_done": "x",
        },
    )
    assert resp.status_code == 404


def test_test_event_endpoint_disabled_returns_409(mock_client, monkeypatch):
    monkeypatch.delenv("MOCK_WEBHOOK_URL", raising=False)
    resp = mock_client.post(
        "/webhooks/test-events",
        json={"event_type": "vehicle.usage.updated", "vehicle_id": "VEH-001"},
    )
    assert resp.status_code == 409


def test_test_event_endpoint_delivers(mock_client, monkeypatch):
    with _Receiver(status=202) as receiver:
        monkeypatch.setenv("MOCK_WEBHOOK_URL", receiver.url)
        monkeypatch.setenv("MOCK_WEBHOOK_SECRET", SECRET)
        resp = mock_client.post(
            "/webhooks/test-events",
            json={"event_type": "vehicle.usage.updated", "vehicle_id": "VEH-001"},
        )

    assert resp.status_code == 200
    assert resp.json()["delivered"] is True
    assert len(receiver.requests) == 1
