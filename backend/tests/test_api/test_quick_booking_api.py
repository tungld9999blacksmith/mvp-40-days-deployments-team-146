"""API-level tests for quick booking (us-061 API-QB-01..04): routing, envelopes, error details.

The real QuickBookingService runs on in-memory SQLite + fakeredis (helpers of
``tests/test_modules/test_quick_booking.py``); only auth and the service factory
are overridden.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from src.common.core.maintenance.booking import Booking
from src.infrastructure.redis import RedisToolkit
from src.main import app
from src.modules.conversation.dependency import get_current_user_id
from src.modules.quick_booking.dependency import get_quick_booking_service
from tests._maintenance import add_booking, make_session
from tests._user_vehicle import add_rules
from tests.test_modules.test_quick_booking import ANCHOR, _owner_with_vehicle, _service, _workshop


@pytest_asyncio.fixture
async def api():
    session = next(make_session())
    redis = FakeAsyncRedis()
    toolkit = RedisToolkit(redis, key_prefix="test", default_cache_ttl=60)
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    service = _service(session, toolkit)
    app.dependency_overrides[get_quick_booking_service] = lambda: service
    app.dependency_overrides[get_current_user_id] = lambda: user.user_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session, user, vehicle, conversation
    app.dependency_overrides.clear()
    await toolkit.pubsub.stop()
    await toolkit.cache.write_back_buffer.stop(final_flush=False)
    await redis.aclose()
    session.close()


def _body(location=True):
    body = {"clientMessageId": str(uuid.uuid4())}
    if location:
        body["location"] = {"lat": ANCHOR[0], "lng": ANCHOR[1]}
    return body


@pytest.mark.asyncio
async def test_chip_then_confirm_over_http(api):
    client, session, user, vehicle, conversation = api
    _workshop(session, "VinFast A", 2)

    created = await client.post(f"/api/v1/conversations/{conversation.id}/quick-booking", json=_body())
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["userMessage"]["content"] == "Đặt lịch bảo dưỡng nhanh"
    card = data["assistantMessage"]["card"]
    assert (card["type"], card["status"]) == ("BOOKING_PROPOSAL", "PROPOSED")
    assert session.exec(select(Booking)).all() == []

    confirmed = await client.post(
        f"/api/v1/conversations/{conversation.id}/booking-proposals/{card['proposalId']}/confirm"
    )
    assert confirmed.status_code == 200
    booking = confirmed.json()["data"]["booking"]
    assert booking["status"] == "CONFIRMED" and booking["bookingCode"].startswith("EVC-")


@pytest.mark.asyncio
async def test_slot_full_error_carries_the_new_proposal(api):
    client, session, user, vehicle, conversation = api
    workshop = _workshop(session, "VinFast A", 2, techs=1)
    _workshop(session, "VinFast B", 5)
    card = (await client.post(f"/api/v1/conversations/{conversation.id}/quick-booking", json=_body())).json()["data"][
        "assistantMessage"
    ]["card"]
    other, other_vehicle, _ = _owner_with_vehicle(
        session, uid="uid-2", email="other@example.com", vin="RLLV00000000000B2", ext="VEH-2"
    )
    add_booking(
        session,
        other,
        other_vehicle,
        workshop,
        d=date.fromisoformat(card["primary"]["date"]),
        t=time.fromisoformat(card["primary"]["timeSlot"]),
        code="EVC-OTHER",
    )

    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/booking-proposals/{card['proposalId']}/confirm"
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "PROPOSAL_SLOT_FULL"
    assert error["details"]["message"]["card"]["proposalId"] == error["details"]["proposalId"]


@pytest.mark.asyncio
async def test_unknown_proposal_is_a_404_and_cancel_is_idempotent(api):
    client, session, user, vehicle, conversation = api
    _workshop(session, "VinFast A", 2)
    missing = "00000000-0000-0000-0000-000000000001"

    response = await client.post(f"/api/v1/conversations/{conversation.id}/booking-proposals/{missing}/confirm")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"

    card = (await client.post(f"/api/v1/conversations/{conversation.id}/quick-booking", json=_body())).json()["data"][
        "assistantMessage"
    ]["card"]
    url = f"/api/v1/conversations/{conversation.id}/booking-proposals/{card['proposalId']}/cancel"
    assert (await client.post(url)).json()["data"]["status"] == "CANCELLED"
    assert (await client.post(url)).status_code == 200
    assert session.exec(select(Booking)).all() == []
