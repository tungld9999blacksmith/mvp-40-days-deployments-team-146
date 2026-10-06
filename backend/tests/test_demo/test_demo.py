import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from src.demo.dependency import make_services
from src.demo.fixtures import WORKSHOP_IDS, ensure_user
from src.demo.knowledge import DemoKnowledge
from src.demo.main import create_app
from src.demo.store import DemoError, DemoStore


class ToolModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        async def reply(messages):
            self.calls += 1
            if isinstance(messages[-1], ToolMessage):
                return AIMessage(content="Đã tra dữ liệu mock MVP.")
            content = messages[-1].content
            name = "propose_booking" if content == "book" else "read_maintenance"
            args = (
                {"workshop_id": WORKSHOP_IDS[0], "date": "2026-10-05", "time_slot": "14:00"}
                if name == "propose_booking"
                else {}
            )
            return AIMessage(content="", tool_calls=[{"id": str(uuid4()), "name": name, "args": args}])

        return RunnableLambda(reply)


@pytest.fixture
def setup():
    clock = [datetime(2026, 10, 4, 9, tzinfo=timezone(timedelta(hours=7)))]
    s = make_services(DemoStore(skip_onboarding=True, clock=lambda: clock[0]))
    model = ToolModel()
    app = create_app(s, token_verifier=lambda token: {"uid": token}, llm_factory=lambda: model)
    with TestClient(app) as client:
        yield s, client, clock, model


def auth(uid="alice"):
    return {"Authorization": f"Bearer {uid}"}


def vehicle(client, uid="alice"):
    return client.get("/api/v1/user-vehicles", headers=auth(uid)).json()["data"][0]["userVehicleId"]


def token(client, uid="alice"):
    return client.get(
        f"/api/v1/workshops/{WORKSHOP_IDS[0]}/availability",
        params={"date": "2026-10-05", "timeSlot": "14:00"},
        headers=auth(uid),
    ).json()["data"]["requested"]["confirmationToken"]


def test_auth_no_sql_and_ownership(setup):
    s, c, _, _ = setup
    assert c.get("/health").json()["storage"] == "memory"
    assert c.get("/api/v1/user-vehicles").status_code == 401
    assert c.post("/api/v1/oauth/sign-in", headers=auth()).json()["data"]["onboarding"]["status"] == "ACTIVE"
    vid = vehicle(c)
    for suffix in ("", "/maintenance-status", "/cost-estimate"):
        assert c.get(f"/api/v1/user-vehicles/{vid}{suffix}", headers=auth("bob")).status_code == 404


def test_showroom_reads_shared_bookings_and_keeps_users_isolated(setup):
    _, c, _, _ = setup
    vid = vehicle(c)
    records = c.get(f"/api/v1/user-vehicles/{vid}/service-records", headers=auth()).json()["data"]["items"]
    assert len(records) == 1 and records[0]["source"] == "OEM"
    assert c.get(f"/api/v1/user-vehicles/{vid}/service-records", headers=auth("bob")).status_code == 404
    response = c.post(
        "/api/v1/bookings",
        headers={**auth(), "Idempotency-Key": "showroom-read"},
        json={"userVehicleId": vid, "confirmationToken": token(c)},
    )
    bid = response.json()["data"]["bookingId"]
    items = c.get("/api/v1/bookings", headers=auth()).json()["data"]["items"]
    assert len(items) == 1 and items[0]["bookingId"] == bid and items[0]["status"] == "CONFIRMED"
    assert c.get("/api/v1/bookings", headers=auth("bob")).json()["data"]["items"] == []
    assert c.get("/api/v1/bookings?scope=PAST", headers=auth()).json()["data"]["items"] == []
    assert c.get("/api/v1/bookings?cursor=-1", headers=auth()).status_code == 400
    feed = c.get("/api/v1/notifications", headers=auth()).json()["data"]["items"]
    assert feed[0]["booking"]["bookingId"] == bid
    assert c.get("/api/v1/notifications", headers=auth("bob")).json()["data"]["items"] == []
    assert c.get(f"/api/v1/bookings/{bid}/progress", headers=auth("bob")).status_code == 404
    assert c.get(f"/api/v1/bookings/{bid}/progress", headers=auth()).json()["data"]["entries"] == []


def test_cost_and_due_are_shared_not_always_overdue(setup):
    s, c, clock, _ = setup
    vid = vehicle(c)
    estimate = c.get(f"/api/v1/user-vehicles/{vid}/cost-estimate", headers=auth()).json()["data"]
    assert estimate["chargeableTotal"] == sum(i["price"] for i in estimate["items"]) == 400000
    s.store.prices[WORKSHOP_IDS[0]]["CABIN_FILTER"] = 100000
    assert s.cost.estimate(1, vid)["chargeableTotal"] == 250000
    s.store.vehicles[vid].update(odoKm=22500, lastServiceDate="2026-10-01")
    assert s.maintenance.calculate(1, vid)["dueStatus"] == "NORMAL"
    s.store.vehicles[vid]["odoKm"] = None
    assert s.maintenance.calculate(1, vid)["dueStatus"] == "UNKNOWN"


def test_vehicle_fixture_matches_oem_snapshot(setup):
    _, c, _, _ = setup
    vid = vehicle(c)
    profile = c.get(f"/api/v1/user-vehicles/{vid}", headers=auth()).json()["data"]
    source = json.loads(
        (Path(__file__).parents[2] / "mock-ev-system/seed-data/ev-mock-dump.json").read_text(encoding="utf-8")
    )["data"]
    usage = next(v for v in source["vehicle_usage"] if v["vehicle_id"] == "VEH-003")
    assert profile["odometer"]["odoKm"] == usage["current_km"]
    assert profile["odometer"]["recordedAt"] == usage["last_updated_at"] + "+00:00"
    policies = {p["policy_id"]: p for p in source["warranty_policies"]}
    expected = {
        (policies[w["policy_id"]]["component"].upper(), w["start_date"], w["end_date"], w["km_limit"])
        for w in source["warranties"]
        if w["vehicle_id"] == "VEH-003"
    }
    assert {(w["component"], w["startDate"], w["endDate"], w["kmLimit"]) for w in profile["warranties"]} == expected


def test_retry_after_token_used_and_conflict(setup):
    s, c, _, _ = setup
    body = {"userVehicleId": vehicle(c), "confirmationToken": token(c)}
    headers = {**auth(), "Idempotency-Key": "one-click"}
    first = c.post("/api/v1/bookings", json=body, headers=headers)
    assert first.status_code == 200
    assert c.post("/api/v1/bookings", json=body, headers=headers).json() == first.json()
    assert len(s.store.bookings) == 1
    assert s.booking.remaining(WORKSHOP_IDS[0], "2026-10-05", "14:00:00") == 0
    assert c.post("/api/v1/bookings", json={**body, "note": "different"}, headers=headers).status_code == 409
    bid = first.json()["data"]["bookingId"]
    assert c.get(f"/api/v1/bookings/{bid}", headers=auth()).json()["data"]["cost"]["amount"] == 400000
    assert c.get(f"/api/v1/bookings/{bid}", headers=auth("bob")).status_code == 404


def test_expired_foreign_and_full_tokens(setup):
    s, c, clock, _ = setup
    alice, bob = vehicle(c), vehicle(c, "bob")
    tok = token(c)
    assert (
        c.post(
            "/api/v1/bookings",
            json={"userVehicleId": bob, "confirmationToken": tok},
            headers={**auth("bob"), "Idempotency-Key": "b"},
        ).status_code
        == 409
    )
    clock[0] += timedelta(minutes=11)
    response = c.post(
        "/api/v1/bookings",
        json={"userVehicleId": alice, "confirmationToken": tok},
        headers={**auth(), "Idempotency-Key": "a"},
    )
    assert response.json()["error"]["code"] == "HOLD_EXPIRED"
    av = c.get(
        f"/api/v1/workshops/{WORKSHOP_IDS[0]}/availability",
        params={"date": "2026-10-05", "timeSlot": "08:30"},
        headers=auth(),
    ).json()["data"]
    assert not av["requested"]["available"] and av["requested"]["confirmationToken"] is None
    assert not s.store.bookings


def test_last_slot_race(setup):
    s, c, _, _ = setup
    alice, bob = vehicle(c), vehicle(c, "bob")
    ta, tb = token(c), token(c, "bob")

    async def race():
        return await asyncio.gather(
            s.booking.create(1, {"userVehicleId": alice, "confirmationToken": ta}, "a"),
            s.booking.create(2, {"userVehicleId": bob, "confirmationToken": tb}, "b"),
            return_exceptions=True,
        )

    results = asyncio.run(race())
    assert sum(isinstance(r, dict) for r in results) == 1
    assert isinstance(results[1], DemoError) and results[1].code == "SLOT_FULL"
    assert len(s.store.bookings) == 1


def sse(response):
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = block.splitlines()
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    return events


def test_graph_sse_proposal_confirm_ticket_reload_replay(setup):
    s, c, _, model = setup
    vid = vehicle(c)
    cid = c.post("/api/v1/conversations", json={"userVehicleId": vid}, headers=auth()).json()["data"]["id"]
    body = {"content": "book", "clientMessageId": "m1"}
    events = sse(c.post(f"/api/v1/conversations/{cid}/messages", json=body, headers=auth()))
    assert events[-1][0] == "message.completed", events
    assert any(e[0] == "status" and e[1].get("tool") == "propose_booking" for e in events)
    card = events[-1][1]["message"]["card"]
    assert card["type"] == "booking_proposal"
    assert "confirmationToken" not in card
    assert not s.store.bookings
    calls = model.calls
    assert sse(c.post(f"/api/v1/conversations/{cid}/messages", json=body, headers=auth()))[-1] == events[-1]
    assert model.calls == calls
    assert c.get(f"/api/v1/booking-proposals/{card['proposalId']}", headers=auth("bob")).status_code == 404
    prepared = c.get(f"/api/v1/booking-proposals/{card['proposalId']}", headers=auth()).json()["data"]
    booking_body = {
        "userVehicleId": vid,
        "confirmationToken": prepared["confirmationToken"],
        "proposalId": card["proposalId"],
    }
    booked = c.post("/api/v1/bookings", json=booking_body, headers={**auth(), "Idempotency-Key": "confirm"})
    assert booked.status_code == 200, booked.text
    bid = booked.json()["data"]["bookingId"]
    assert c.get(f"/api/v1/bookings/{bid}", headers=auth()).json()["data"]["conversationId"] == cid
    history = c.get(f"/api/v1/conversations/{cid}/messages", headers=auth()).json()["data"]
    assert history[-1]["refs"]["bookingId"] == bid
    assert len(history) == 4
    assert c.get(f"/api/v1/conversations/{cid}/messages", headers=auth("bob")).status_code == 404
    assert c.post("/api/v1/demo/reset", headers=auth()).status_code == 200
    assert not s.store.bookings and not s.store.conversations


def test_sources_are_actual_excerpts_and_missing_topic():
    k = DemoKnowledge()
    found = k.search("Bảo dưỡng định kỳ có được bảo hành không?")
    assert found["status"] == "ok"
    assert any("Bảo hành sẽ không được áp dụng" in c["snippet"] for c in found["data"]["citations"])
    assert k.search("Áp suất lốp VF6 bao nhiêu?")["code"] == "NO_EVIDENCE"


def test_llm_failure_not_success(setup):
    s, c, _, _ = setup

    def fail():
        raise RuntimeError("private diagnostic")

    c.app.state.chat.llm_factory = fail
    cid = c.post("/api/v1/conversations", json={"userVehicleId": vehicle(c)}, headers=auth()).json()["data"]["id"]
    events = sse(
        c.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "question", "clientMessageId": "m1"},
            headers=auth(),
        )
    )
    assert events[-1][0] == "error"
    assert "private diagnostic" not in str(events)
    assert not s.store.bookings


def test_validation_does_not_echo_confirmation_token(setup):
    _, c, _, _ = setup
    response = c.post(
        "/api/v1/bookings",
        json={"userVehicleId": "bad-id", "confirmationToken": "private-token"},
        headers={**auth(), "Idempotency-Key": "one"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "private-token" not in response.text


def test_second_turn_keeps_history_once(setup):
    _, c, _, model = setup
    cid = c.post("/api/v1/conversations", json={"userVehicleId": vehicle(c)}, headers=auth()).json()["data"]["id"]
    for mid in ("m1", "m2"):
        events = sse(
            c.post(
                f"/api/v1/conversations/{cid}/messages",
                json={"content": "maintenance", "clientMessageId": mid},
                headers=auth(),
            )
        )
        assert events[-1][0] == "message.completed"
    state = asyncio.run(c.app.state.chat.graph.aget_state({"configurable": {"thread_id": cid}}))
    assert len(state.values["messages"]) == 8  # human + tool call + result + final = 4 each
    assert len(c.get(f"/api/v1/conversations/{cid}/messages", headers=auth()).json()["data"]) == 4
    assert model.calls == 4


def test_reset_preserves_other_users(setup):
    s, c, _, _ = setup
    alice, bob = vehicle(c), vehicle(c, "bob")
    for uid, vid in [("alice", alice), ("bob", bob)]:
        c.post("/api/v1/conversations", json={"userVehicleId": vid}, headers=auth(uid))
    assert c.post("/api/v1/demo/reset", headers=auth()).status_code == 200
    assert len(s.store.conversations) == 1
    assert c.get("/api/v1/conversations", headers=auth("bob")).json()["data"][0]["userVehicleId"] == bob


def test_proposal_rejects_mismatched_token_and_rechecks_taken_slot(setup):
    s, c, _, _ = setup
    va, vb = vehicle(c), vehicle(c, "bob")
    convo = s.messages.create(1, va)
    question = s.messages.append(convo["id"], "user", "book")
    card = s.booking.proposal(1, va, convo["id"], question["id"], WORKSHOP_IDS[0], "2026-10-05", "14:00")
    wrong = s.booking.availability(1, WORKSHOP_IDS[1], "2026-10-05", "14:00")["requested"]["confirmationToken"]
    response = c.post(
        "/api/v1/bookings",
        json={"userVehicleId": va, "confirmationToken": wrong, "proposalId": card["proposalId"]},
        headers={**auth(), "Idempotency-Key": "wrong-slot"},
    )
    assert response.json()["error"]["code"] == "INVALID_CONFIRMATION_TOKEN"
    assert (
        c.post(
            "/api/v1/bookings",
            json={"userVehicleId": vb, "confirmationToken": token(c, "bob")},
            headers={**auth("bob"), "Idempotency-Key": "last-slot"},
        ).status_code
        == 200
    )
    assert (
        c.get(f"/api/v1/booking-proposals/{card['proposalId']}", headers=auth()).json()["error"]["code"] == "SLOT_FULL"
    )
    assert len(s.store.bookings) == 1
