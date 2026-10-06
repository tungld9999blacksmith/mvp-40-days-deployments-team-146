"""Verify the owner/workshop loop, permissions, conflicts and capacity."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.demo.dependency import make_services
from src.demo.fixtures import WORKSHOP_IDS
from src.demo.main import create_app
from src.demo.store import DemoStore


def headers(uid="driver"):
    return {"Authorization": f"Bearer {uid}"}


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.delenv("DEMO_WORKSHOP_OWNERS", raising=False)
    clock = [datetime(2026, 10, 4, 9, tzinfo=timezone(timedelta(hours=7)))]
    services = make_services(DemoStore(skip_onboarding=True, clock=lambda: clock[0]))

    def verify(uid):
        return {"uid": uid, "email": f"{uid}@example.com", "email_verified": uid != "unverified", "name": uid}

    with TestClient(create_app(services, token_verifier=verify)) as client:
        yield services, client, clock


def book(c, *, day="2026-10-04", uid="driver", wid=WORKSHOP_IDS[0], chat=False):
    vid = c.get("/api/v1/user-vehicles", headers=headers(uid)).json()["data"][0]["userVehicleId"]
    av = c.get(
        f"/api/v1/workshops/{wid}/availability", params={"date": day, "timeSlot": "14:00"}, headers=headers(uid)
    ).json()["data"]
    payload = {"userVehicleId": vid, "confirmationToken": av["requested"]["confirmationToken"]}
    if chat:
        cid = c.post("/api/v1/conversations", json={"userVehicleId": vid}, headers=headers(uid)).json()["data"]["id"]
        s = c.app.state.services
        p = s.booking.proposal(s.store.users[uid]["userId"], vid, cid, None, wid, day, "14:00")
        payload["proposalId"] = p["proposalId"]
    response = c.post(
        "/api/v1/bookings", json=payload, headers={**headers(uid), "Idempotency-Key": f"booking-{uid}-{day}"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def change(c, bid, action, expected, uid="workshop1", **extra):
    return c.post(
        f"/api/v1/workshop-owner/bookings/{bid}/transitions",
        headers=headers(uid),
        json={"action": action, "expectedStatus": expected, **extra},
    )


def test_workshop_login_session_reload_and_role_scope(demo):
    s, c, _ = demo
    assert c.post("/api/v1/workshop-owner/oauth/sign-in").status_code == 401
    for uid in ("driver", "unverified"):
        assert c.post("/api/v1/workshop-owner/oauth/sign-in", headers=headers(uid)).status_code == 403
    data = c.post("/api/v1/workshop-owner/oauth/sign-in", headers=headers("workshop1")).json()["data"]
    assert data["onboarding"]["nextStep"] == "DASHBOARD"
    assert data["workshop"]["workshopId"] == WORKSHOP_IDS[0]
    assert s.store.users == {}  # Workshop login does not fabricate a vehicle owner.
    assert (
        c.get("/api/v1/workshop-owner/oauth/session", headers=headers("workshop1")).json()["data"]["ownerId"]
        == data["owner"]["ownerId"]
    )
    assert (
        c.get("/api/v1/workshop-owner/onboarding", headers=headers("workshop1")).json()["data"]["workshop"]["name"]
        == data["workshop"]["name"]
    )
    assert c.post("/api/v1/workshop-owner/oauth/logout", headers=headers("workshop1")).status_code == 204


def test_shared_board_permissions_and_validated_filters(demo):
    _, c, _ = demo
    b = book(c)
    bid = b["bookingId"]
    data = c.get("/api/v1/workshop-owner/bookings", headers=headers("workshop1")).json()["data"]
    assert data["summary"]["CONFIRMED"] == 1
    assert data["items"][0]["bookingCode"] == b["bookingCode"]
    assert "email" not in data["items"][0]["customer"]
    assert c.get("/api/v1/workshop-owner/bookings", headers=headers("workshop2")).json()["data"]["items"] == []
    assert c.get(f"/api/v1/workshop-owner/bookings/{bid}", headers=headers("workshop2")).status_code == 404
    assert change(c, bid, "CANCEL", "CONFIRMED", "workshop2", note="Cancel", reasonCode="OTHER").status_code == 404
    assert c.get(f"/api/v1/bookings/{bid}", headers=headers("someone-else")).status_code == 404
    for query in ("from=2026-10-04&to=2026-12-04", "q=x", "from=2026-10-05&to=2026-10-04"):
        assert c.get(f"/api/v1/workshop-owner/bookings?{query}", headers=headers("workshop1")).status_code == 400
    assert (
        c.get("/api/v1/workshop-owner/bookings?status=CANCELLED", headers=headers("workshop1")).json()["data"]["items"]
        == []
    )


def test_service_transitions_are_shared_and_keep_slot_occupied(demo):
    s, c, _ = demo
    b = book(c, chat=True)
    bid = b["bookingId"]
    assert change(c, bid, "START", "CONFIRMED").status_code == 409
    assert change(c, bid, "CHECK_IN", "CONFIRMED").json()["data"]["status"] == "CHECKED_IN"
    assert change(c, bid, "CHECK_IN", "CONFIRMED").status_code == 409
    assert s.booking.remaining(WORKSHOP_IDS[0], "2026-10-04", "14:00:00") == 0
    assert change(c, bid, "START", "CHECKED_IN").status_code == 200
    assert change(c, bid, "COMPLETE", "IN_PROGRESS").status_code == 400
    assert change(c, bid, "COMPLETE", "IN_PROGRESS", actualCost=-1).status_code == 422
    assert change(c, bid, "COMPLETE", "IN_PROGRESS", actualCost=350000).json()["data"]["status"] == "COMPLETED"
    ticket = c.get(f"/api/v1/bookings/{bid}", headers=headers()).json()["data"]
    assert ticket["status"] == "completed" and ticket["actualCost"] == 350000
    assert [e["toStatus"] for e in ticket["history"]] == ["CONFIRMED", "CHECKED_IN", "IN_PROGRESS", "COMPLETED"]
    messages = c.get(f"/api/v1/conversations/{ticket['conversationId']}/messages", headers=headers()).json()["data"]
    assert messages[-1]["refs"]["bookingId"] == bid and "COMPLETED" in messages[-1]["content"]
    assert s.booking.remaining(WORKSHOP_IDS[0], "2026-10-04", "14:00:00") == 0
    assert c.get("/api/v1/bookings", headers=headers()).json()["data"]["items"] == []
    past = c.get("/api/v1/bookings?scope=PAST", headers=headers()).json()["data"]["items"]
    assert past[0]["bookingId"] == bid and past[0]["status"] == "COMPLETED"
    records = c.get(f"/api/v1/user-vehicles/{s.store.bookings[bid]['userVehicleId']}/service-records", headers=headers()).json()[
        "data"
    ]["items"]
    assert records[0]["bookingId"] == bid and records[0]["actualCost"] == 350000
    progress = c.get(f"/api/v1/bookings/{bid}/progress", headers=headers()).json()["data"]
    assert progress["isFrozen"] and progress["currentStage"] == "READY_FOR_PICKUP"
    assert len(progress["entries"]) == 3


def test_qr_lookup_is_scoped_and_uses_booking_state(demo):
    _, c, _ = demo
    b = book(c)
    bid, code = b["bookingId"], b["bookingCode"]
    owner_url = f"/api/v1/bookings/by-code/{code.lower()}"
    shop_url = f"/api/v1/workshop-owner/bookings/by-code/{code}"
    assert c.get(owner_url, headers=headers()).json()["data"]["bookingId"] == bid
    assert c.get(owner_url, headers=headers("someone-else")).status_code == 404
    assert c.get(shop_url, headers=headers("workshop2")).status_code == 404
    assert c.get(shop_url, headers=headers("workshop1")).json()["data"]["checkInEligibility"] == "ELIGIBLE"
    assert change(c, bid, "CHECK_IN", "CONFIRMED", source="QR_SCAN").status_code == 200
    lookup = c.get(shop_url, headers=headers("workshop1")).json()["data"]
    assert lookup["checkInEligibility"] == "ALREADY_CHECKED_IN" and lookup["checkedInAt"]
    slots = c.get("/api/v1/workshop-owner/capacity?from=2026-10-04", headers=headers("workshop1")).json()["data"][
        "days"
    ][0]["slots"]
    slot = next(slot for slot in slots if slot["timeSlot"] == "14:00:00")
    assert slot["occupied"] == 1 and slot["remaining"] == 0


def test_tomorrow_cannot_check_in_cancel_frees_capacity(demo):
    s, c, _ = demo
    b = book(c, day="2026-10-05")
    bid = b["bookingId"]
    assert change(c, bid, "CHECK_IN", "CONFIRMED").status_code == 409
    assert change(c, bid, "CANCEL", "CONFIRMED").status_code == 400
    assert change(c, bid, "CANCEL", "CONFIRMED", reasonCode="OTHER", note="Khách đổi lịch").status_code == 200
    assert c.get(f"/api/v1/bookings/{bid}", headers=headers()).json()["data"]["status"] == "cancelled"
    assert s.booking.remaining(WORKSHOP_IDS[0], "2026-10-05", "14:00:00") == 1


def test_configured_account_requires_verified_email(demo, monkeypatch):
    _, c, _ = demo
    monkeypatch.setenv("DEMO_WORKSHOP_OWNERS", '{"unverified@example.com":"' + WORKSHOP_IDS[0] + '"}')
    assert c.post("/api/v1/workshop-owner/oauth/sign-in", headers=headers("unverified")).status_code == 403
    monkeypatch.setenv("DEMO_WORKSHOP_OWNERS", '{"manager@example.com":"' + WORKSHOP_IDS[1] + '"}')
    assert (
        c.post("/api/v1/workshop-owner/oauth/sign-in", headers=headers("manager")).json()["data"]["workshop"][
            "workshopId"
        ]
        == WORKSHOP_IDS[1]
    )
    monkeypatch.setenv("DEMO_WORKSHOP_OWNERS", "[]")
    assert c.post("/api/v1/workshop-owner/oauth/sign-in", headers=headers("manager")).status_code == 503
