import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from src.agents.context import AgentCtx
from src.demo.adapters import build_tools
from src.demo.dependency import make_services
from src.demo.fixtures import WORKSHOP_IDS, ensure_user
from src.demo.main import create_app
from src.demo.notification_persistence import load_notifications
from src.demo.notifications import DemoEmailConfig, SettingsUpdate
from src.demo.store import DemoError, DemoStore
from src.modules.notification.channels import DeliveryResult
from src.modules.notification.email_transport import ResendEmailTransport, verify_webhook


@pytest.fixture
def rig():
    clock = [datetime(2026, 10, 6, 9, tzinfo=timezone(timedelta(hours=7)))]
    services = make_services(DemoStore(skip_onboarding=True, clock=lambda: clock[0]))
    user = ensure_user(services.store, {"uid": "alice", "email": "alice@example.com", "email_verified": True})
    vehicle = next(iter(services.store.vehicles.values()))
    return services, user, vehicle, clock


def enable(services, user, **kwargs):
    return services.notifications.update(
        user["userId"],
        SettingsUpdate.model_validate(
            {
                "remindersEnabled": True,
                "channels": [{"channel": "EMAIL", "enabled": True}],
                **kwargs,
            }
        ),
    )


def run(services):
    return asyncio.run(services.notifications.run())


def test_opt_in_and_identity_refresh(rig):
    services, user, vehicle, _ = rig
    run(services)
    assert not services.store.email_deliveries
    ensure_user(services.store, {"uid": "alice", "email": "alice@example.com", "email_verified": False})
    with pytest.raises(DemoError, match="xác minh"):
        enable(services, user)
    assert not services.store.notification_preferences
    ensure_user(services.store, {"uid": "alice", "email": "alice@example.com", "email_verified": True})
    state = enable(services, user)
    assert state["emailScope"] == "MAINTENANCE_REMINDER" and state["scope"] == "ALL_OWNED_VEHICLES"
    assert state["channels"][0]["status"] == "CONNECTED"
    user["emailVerified"] = False
    run(services)
    assert not services.store.email_deliveries
    assert next(iter(services.store.reminders.values()))["emailSkipReason"] == "NO_VERIFIED_RECIPIENT"


@pytest.mark.parametrize(
    ("odo", "last_date", "reason"),
    [
        (23500, "2026-10-01", "KM"),
        (10000, "2025-10-08", "TIME"),
        (None, "2025-10-08", "TIME"),
    ],
)
def test_km_or_days_and_time_without_odo(rig, odo, last_date, reason):
    services, user, vehicle, _ = rig
    vehicle.update(odoKm=odo, lastServiceDate=last_date)
    enable(services, user)
    run(services)
    reminder = next(iter(services.store.reminders.values()))
    assert reminder["details"]["reason"] == reason and reminder["level"] == "EARLY"
    delivery = next(iter(services.store.email_deliveries.values()))
    assert delivery["status"] == "SENT" and delivery["deliveryState"] == "mock"
    assert "51A-11111" not in delivery["payload"]["body"]
    assert "VIN" not in delivery["payload"]["body"]
    if odo is None:
        assert "Chưa có ODO" in delivery["payload"]["body"]


def test_lead_days_distinct_from_due_soon_and_unknown(rig, monkeypatch):
    services, user, vehicle, _ = rig
    vehicle.update(odoKm=10000, lastServiceDate="2025-10-10")
    enable(services, user)
    assert services.maintenance.calculate(user["userId"], vehicle["userVehicleId"])["dueStatus"] == "DUE_SOON"
    run(services)
    assert not services.store.reminders  # Four days away, preference is two.
    services.notifications.update(user["userId"], SettingsUpdate(reminderLeadDays=7))
    run(services)
    assert len(services.store.email_deliveries) == 1
    services.store.reminders.clear()
    original = services.maintenance.calculate
    monkeypatch.setattr(
        services.maintenance,
        "calculate",
        lambda *args: {
            **original(*args),
            "dueStatus": "UNKNOWN",
            "unknownReason": "NO_MAINTENANCE_RULE",
        },
    )
    run(services)
    assert not services.store.reminders


def test_concurrent_runs_and_early_to_expired_cooldown(rig):
    services, user, vehicle, clock = rig
    vehicle.update(odoKm=23500, lastServiceDate="2026-10-01")
    enable(services, user)

    async def concurrent():
        await asyncio.gather(services.notifications.run(), services.notifications.run())

    asyncio.run(concurrent())
    assert len(services.store.reminders) == len(services.store.email_deliveries) == 1
    vehicle["odoKm"] = 24100
    clock[0] += timedelta(days=1)
    run(services)
    assert len(services.store.reminders) == 2
    assert len(services.store.email_deliveries) == 1
    early = next(r for r in services.store.reminders.values() if r["level"] == "EARLY")
    assert early["resolutionReason"] == "SUPERSEDED"
    clock[0] += timedelta(days=6)
    run(services)
    assert len(services.store.email_deliveries) == 2
    run(services)
    assert all(d["attempts"] == 1 for d in services.store.email_deliveries.values())
    vehicle["odoKm"] = 23500  # An OEM correction removes the overdue condition.
    run(services)
    assert not early["resolved"]
    expired = next(r for r in services.store.reminders.values() if r["level"] == "EXPIRED")
    assert expired["resolutionReason"] == "STATUS_CHANGED"
    assert len(services.store.email_deliveries) == 2


def test_booking_matching_cancellation_and_completion(rig):
    services, user, vehicle, clock = rig
    enable(services, user)
    run(services)
    reminder = next(iter(services.store.reminders.values()))
    booking = {
        "userVehicleId": vehicle["userVehicleId"],
        "userId": user["userId"],
        "odoMilestone": 12000,
        "status": "confirmed",
        "bookingDate": clock[0].date().isoformat(),
        "workshopId": WORKSHOP_IDS[0],
    }
    services.store.bookings["booking"] = booking
    run(services)
    assert not reminder["resolved"]
    booking["odoMilestone"] = 24000
    assert services.notifications.context(user["userId"], reminder["id"])["hasCurrentBooking"]
    run(services)
    assert reminder["resolutionReason"] == "HAS_BOOKING"
    booking["status"] = "cancelled"
    run(services)
    assert not reminder["resolved"] and len(services.store.email_deliveries) == 1
    services.notifications.complete_maintenance(booking)
    assert reminder["resolutionReason"] == "MAINTENANCE_COMPLETED"
    assert (
        services.maintenance.calculate(user["userId"], vehicle["userVehicleId"])["nextMilestone"]["odoMilestoneKm"]
        == 48000
    )
    run(services)
    assert len(services.store.email_deliveries) == 1


def test_restart_preserves_cooldown_payload_and_reset(rig, tmp_path):
    services, user, vehicle, clock = rig
    services.store.notifications_path = tmp_path / "notifications.json"
    enable(services, user)
    run(services)
    snapshot = json.loads(services.store.notifications_path.read_text(encoding="utf-8"))
    resumed = make_services(DemoStore(skip_onboarding=True, clock=lambda: clock[0]))
    # UID is stable even when the in-memory numeric ID differs after restart.
    ensure_user(resumed.store, {"uid": "bob"})
    ensure_user(resumed.store, {"uid": "alice", "email": user["email"], "email_verified": True})
    load_notifications(resumed.store, services.store.notifications_path)
    run(resumed)
    assert resumed.store.email_deliveries == snapshot["email_deliveries"]
    app = create_app(
        resumed, token_verifier=lambda token: {"uid": token, "email": user["email"], "email_verified": True}
    )
    with TestClient(app) as client:
        assert client.post("/api/v1/demo/reset", headers={"Authorization": "Bearer alice"}).status_code == 200
        assert len(resumed.store.email_deliveries) == 1
        assert (
            client.get("/api/v1/demo/email-outbox", headers={"Authorization": "Bearer bob"}).json()["data"]["items"]
            == []
        )


class RecordingTransport:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    async def send(self, recipient, message):
        self.calls.append((recipient, message))
        return self.responses.pop(0)


def real_mode(services, transport):
    services.notifications.config = DemoEmailConfig(
        mode="resend",
        sender="EV Care <sender@example.com>",
        api_key="test",
        webhook_secret="whsec_dGVzdA==",
    )
    services.notifications.transport = transport


def test_retry_immutable_payload_and_no_blind_retry_after_window(rig):
    services, user, vehicle, clock = rig
    transport = RecordingTransport([DeliveryResult.failed("TIMEOUT"), DeliveryResult.sent("provider-1")])
    real_mode(services, transport)
    enable(services, user)
    run(services)
    vehicle["odoKm"] = 40000
    run(services)
    assert len(transport.calls) == 1
    clock[0] += timedelta(minutes=5)
    run(services)
    assert len(transport.calls) == 2 and transport.calls[0] == transport.calls[1]
    delivery = next(iter(services.store.email_deliveries.values()))
    assert delivery["providerMessageId"] == "provider-1"
    assert "38,210" in delivery["payload"]["body"]
    delivery.update(status="FAILED", errorCode="TIMEOUT", nextAttemptAt=None)
    clock[0] += timedelta(hours=24)
    run(services)
    assert delivery["errorCode"] == "RECONCILIATION_REQUIRED" and len(transport.calls) == 2


def test_opt_out_and_email_change_stop_pending_retry(rig):
    services, user, vehicle, clock = rig
    transport = RecordingTransport([DeliveryResult.failed("TIMEOUT")])
    real_mode(services, transport)
    enable(services, user)
    run(services)
    clock[0] += timedelta(minutes=5)
    services.notifications.update(user["userId"], SettingsUpdate(channels=[{"channel": "EMAIL", "enabled": False}]))
    run(services)
    assert len(transport.calls) == 1
    enable(services, user)
    user["email"] = "changed@example.com"
    run(services)
    assert len(transport.calls) == 1
    assert next(iter(services.store.email_deliveries.values()))["errorCode"] == "DELIVERY_CONTEXT_CHANGED"


def test_webhook_before_response_timeout_and_bounce(rig):
    services, user, vehicle, clock = rig

    class EarlyWebhook:
        async def send(self, recipient, message):
            payload = {
                "type": "email.bounced",
                "created_at": clock[0].isoformat(),
                "data": {
                    "email_id": "provider-early",
                    "tags": {"delivery_id": message.delivery_id},
                },
            }
            assert services.notifications.webhook("event-1", payload)["received"]
            assert services.notifications.webhook("event-1", payload)["duplicate"]
            return DeliveryResult.failed("TIMEOUT")

    real_mode(services, EarlyWebhook())
    enable(services, user)
    run(services)
    delivery = next(iter(services.store.email_deliveries.values()))
    assert delivery["providerMessageId"] == "provider-early"
    assert delivery["deliveryState"] == "bounced" and delivery["errorCode"] == "EMAIL_BOUNCED"
    assert services.notifications.settings(user["userId"])["emailSuppressed"]
    services.notifications.webhook(
        "event-2",
        {"type": "email.delivered", "created_at": clock[0].isoformat(), "data": {"email_id": "provider-early"}},
    )
    assert delivery["deliveryState"] == "bounced"
    with pytest.raises(DemoError, match="chặn"):
        enable(services, user)


def test_api_validation_scope_and_unsigned_webhook(rig):
    services, user, vehicle, _ = rig

    def claims(uid):
        return {"uid": uid, "email": f"{uid}@example.com", "email_verified": True}

    app = create_app(services, token_verifier=claims)
    headers = {"Authorization": "Bearer alice"}
    with TestClient(app) as client:
        assert (
            client.put("/api/v1/notification-settings", headers=headers, json={"reminderLeadDays": 31}).status_code
            == 422
        )
        assert (
            client.put(
                "/api/v1/notification-settings", headers=headers, json={"emailRecipient": "other@example.com"}
            ).status_code
            == 422
        )
        assert (
            client.put("/api/v1/notification-settings", headers=headers, json={"remindersEnabled": None}).status_code
            == 422
        )
        enable(services, user)
        assert client.post("/api/v1/demo/reminders/run", headers=headers).status_code == 200
        rid = next(iter(services.store.reminders))
        assert (
            client.get(f"/api/v1/notifications/reminders/{rid}", headers={"Authorization": "Bearer bob"}).status_code
            == 404
        )
        assert client.get(f"/api/v1/notifications/reminders/{rid}", headers=headers).status_code == 200
        real_mode(services, RecordingTransport([]))
        assert client.post("/api/v1/notifications/email/webhook", json={}).status_code == 401


def test_agent_settings_and_context_share_service_and_hide_identity(rig):
    services, user, vehicle, _ = rig
    tools = {tool.name: tool for tool in build_tools(services)}
    config = {"configurable": {"ctx": AgentCtx(user["userId"], vehicle["userVehicleId"], str(uuid4()))}}

    async def invoke():
        result = json.loads(
            await tools["update_reminder_settings"].ainvoke(
                {
                    "reminders_enabled": True,
                    "email_enabled": True,
                    "reminder_lead_days": 7,
                },
                config,
            )
        )
        assert result["status"] == "ok" and result["data"]["reminderLeadDays"] == 7
        assert not services.store.email_deliveries  # Tools do not dispatch.
        await services.notifications.run()
        context = json.loads(await tools["get_reminder_context"].ainvoke({}, config))
        assert context["status"] == "ok" and context["data"]["details"]["reason"] == "BOTH"
        user["emailVerified"] = False
        denied = json.loads(await tools["update_reminder_settings"].ainvoke({"email_enabled": True}, config))
        assert denied["status"] == "error" and denied["code"] == "EMAIL_NOT_VERIFIED"

    asyncio.run(invoke())
    for name in ("get_reminder_settings", "update_reminder_settings", "get_reminder_context"):
        properties = tools[name].tool_call_schema.model_json_schema()["properties"]
        assert not {"config", "user_id", "vehicle_id", "email", "recipient"}.intersection(properties)


def test_agent_http_sse_settings_context_replay_and_ownership_without_external_llm(rig):
    """Exercise the actual graph/tools/SSE; model responses are local test inputs."""
    services, user, vehicle, _ = rig

    class LocalToolModel:
        def __init__(self):
            self.calls = 0
            self.outputs = []
            self.script = {
                "enable": (
                    "update_reminder_settings",
                    {"reminders_enabled": True, "email_enabled": True, "reminder_lead_days": 7},
                ),
                "read": ("get_reminder_settings", {}),
                "disable": ("update_reminder_settings", {"email_enabled": False}),
            }

        def bind_tools(self, tools):
            async def reply(messages):
                self.calls += 1
                if isinstance(messages[-1], ToolMessage):
                    self.outputs.append(json.loads(messages[-1].content))
                    return AIMessage(content="Kết quả từ tool kiểm thử cục bộ.")
                name, args = self.script[messages[-1].content]
                return AIMessage(content="", tool_calls=[{"id": str(uuid4()), "name": name, "args": args}])

            return RunnableLambda(reply)

    model = LocalToolModel()
    app = create_app(
        services,
        token_verifier=lambda uid: {"uid": uid, "email": f"{uid}@example.com", "email_verified": True},
        llm_factory=lambda: model,
    )
    # Keep the scheduler controlled; no TestClient lifespan background task.
    client = TestClient(app)
    try:
        headers = {"Authorization": "Bearer alice"}
        cid = client.post(
            "/api/v1/conversations", headers=headers, json={"userVehicleId": vehicle["userVehicleId"]}
        ).json()["data"]["id"]

        def send(content, message_id, tool):
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=headers,
                json={"content": content, "clientMessageId": message_id},
            )
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert "event: message.completed" in response.text and "event: error" not in response.text
            if tool:
                assert f'"tool": "{tool}"' in response.text
            return response.text

        send("enable", "enable-1", "update_reminder_settings")
        state = client.get("/api/v1/notification-settings", headers=headers).json()["data"]
        assert state["remindersEnabled"] and state["reminderLeadDays"] == 7
        assert state["channels"][0]["enabled"] and model.outputs[-1]["status"] == "ok"
        calls = model.calls
        replay = send("enable", "enable-1", None)
        assert '"replayed": true' in replay and model.calls == calls
        assert not services.store.email_deliveries  # Settings tools do not send email.

        run(services)
        rid = next(iter(services.store.reminders))
        model.script["explain"] = ("get_reminder_context", {"reminder_id": rid})
        send("explain", "explain-1", "get_reminder_context")
        result = model.outputs[-1]
        assert result["status"] == "ok" and result["data"]["details"]["reason"] == "BOTH"
        assert result["data"]["deliveries"][0]["deliveryState"] == "mock"
        send("read", "read-1", "get_reminder_settings")
        assert model.outputs[-1]["data"]["reminderLeadDays"] == 7

        other = ensure_user(services.store, {"uid": "bob", "email": "bob@example.com", "email_verified": True})
        enable(services, other)
        run(services)
        foreign_rid = next(r["id"] for r in services.store.reminders.values() if r["uid"] == "bob")
        model.script["foreign"] = ("get_reminder_context", {"reminder_id": foreign_rid})
        outputs_before = len(model.outputs)
        reply = send("foreign", "foreign-1", "get_reminder_context")
        # A failed tool ends the turn with a fixed reply (guardrails.tool_failure): the
        # model never sees the result, so nothing about Bob's reminder can reach it.
        assert len(model.outputs) == outputs_before
        completed = reply.split("event: message.completed\ndata: ", 1)[1].split("\n", 1)[0]
        answer = json.loads(completed)["message"]["content"]
        assert "Chưa có kết quả thành công" in answer and foreign_rid not in reply and "bob" not in reply
        tools = {tool.name: tool for tool in build_tools(services)}
        config = {"configurable": {"ctx": AgentCtx(user["userId"], vehicle["userVehicleId"], cid)}}
        foreign = json.loads(asyncio.run(tools["get_reminder_context"].ainvoke({"reminder_id": foreign_rid}, config)))
        assert foreign["status"] == "error" and foreign["code"] == "REMINDER_NOT_FOUND"
        assert foreign["data"] == {}

        send("disable", "disable-1", "update_reminder_settings")
        state = client.get("/api/v1/notification-settings", headers=headers).json()["data"]
        assert state["remindersEnabled"] and not state["channels"][0]["enabled"]
        assert state["reminderLeadDays"] == 7
        owner_deliveries = [
            delivery for delivery in services.store.email_deliveries.values() if delivery["uid"] == "alice"
        ]
        run(services)
        assert [
            delivery for delivery in services.store.email_deliveries.values() if delivery["uid"] == "alice"
        ] == owner_deliveries
    finally:
        client.close()


def test_svix_published_vector_and_replay_window():
    raw = b'{"event_type":"ping","data":{"success":true}}'
    headers = {
        "svix-id": "msg_loFOjxBNrRLzqYUf",
        "svix-timestamp": "1731705121",
        "svix-signature": "v1,rAvfW3dJ/X/qxhsaXPOyyCGmRKsaKWcsNccKXlIktD0=",
    }
    secret = "whsec_plJ3nmyCDGBKInavdOK15jsl"
    assert verify_webhook(raw, headers, secret, now=1731705121) == headers["svix-id"]
    with pytest.raises(ValueError):
        verify_webhook(raw + b" ", headers, secret, now=1731705121)
    with pytest.raises(ValueError):
        verify_webhook(raw, headers, secret, now=1731705422)


def test_signed_http_webhook_deduplication_and_early_arrival(rig):
    services, user, vehicle, clock = rig
    real_mode(services, RecordingTransport([DeliveryResult.sent("provider-delivered")]))
    enable(services, user)
    raw = json.dumps(
        {
            "type": "email.delivered",
            "created_at": clock[0].isoformat(),
            "data": {
                "email_id": "provider-delivered",
            },
        }
    ).encode()
    timestamp = str(int(time.time()))
    signature = base64.b64encode(
        hmac.new(b"test", f"event-http.{timestamp}.".encode() + raw, hashlib.sha256).digest()
    ).decode()
    headers = {"svix-id": "event-http", "svix-timestamp": timestamp, "svix-signature": f"v1,{signature}"}
    app = create_app(services, token_verifier=lambda uid: {"uid": uid})
    # No lifespan: explicitly control the worker so the event arrives before dispatch.
    client = TestClient(app)
    assert client.post("/api/v1/notifications/email/webhook", content=raw, headers=headers).status_code == 200
    assert not services.store.email_events["event-http"]["applied"]
    run(services)
    delivery = next(iter(services.store.email_deliveries.values()))
    assert delivery["deliveryState"] == "delivered"
    assert client.post("/api/v1/notifications/email/webhook", content=raw, headers=headers).json()["data"]["duplicate"]
    assert client.post("/api/v1/notifications/email/webhook", content=raw + b" ", headers=headers).status_code == 401


def test_stale_odo_and_html_escaping(rig):
    services, user, vehicle, clock = rig
    vehicle.update(
        modelName='<img src=x onerror="alert(1)">', odoRecordedAt=(clock[0] - timedelta(days=45)).isoformat()
    )
    enable(services, user)
    run(services)
    message = next(iter(services.store.email_deliveries.values()))["payload"]
    assert "Dữ liệu ODO đã cũ" in message["body"]
    assert "&lt;img" in message["html"] and "<img" not in message["html"]


def test_emulator_cannot_enable_real_delivery_from_env(monkeypatch):
    monkeypatch.setenv("DEMO_EMAIL_MODE", "resend")
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    with pytest.raises(ValueError, match="real Firebase"):
        DemoEmailConfig.from_env()
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST")
    monkeypatch.setenv("DEMO_NOW", "2026-10-06T09:00:00+07:00")
    with pytest.raises(ValueError, match="real clock"):
        DemoEmailConfig.from_env()


def test_resend_transport_retries_same_key_and_scope(rig):
    services, user, _, _ = rig
    enable(services, user)
    run(services)
    from src.modules.notification.channels import NotificationMessage

    message = NotificationMessage(**next(iter(services.store.email_deliveries.values()))["payload"])
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429 if len(requests) == 1 else 200, json={"id": "provider-http"})

    transport = ResendEmailTransport(
        "test", client_factory=lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw)
    )

    async def invoke():
        assert (await transport.send(user["email"], message)).error_code == "RATE_LIMITED"
        assert (await transport.send(user["email"], message)).provider_message_id == "provider-http"
        assert (
            await transport.send(user["email"], NotificationMessage("booking", "body"))
        ).error_code == "EMAIL_MAINTENANCE_ONLY"

    asyncio.run(invoke())
    assert requests[0].headers["Idempotency-Key"] == requests[1].headers["Idempotency-Key"]
    assert json.loads(requests[0].content) == json.loads(requests[1].content)
