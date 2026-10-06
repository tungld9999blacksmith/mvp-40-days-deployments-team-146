"""The public booking endpoint must honor retries, including overlapping requests."""

import asyncio
from datetime import time, timedelta

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, select

from src.common.core.maintenance.booking import Booking
from src.infrastructure.redis import RedisToolkit
from src.main import app
from src.modules.booking.dependency import get_booking_service, require_active_vehicle_owner
from src.modules.booking.domain import BookingConfig, now_vn
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.booking.service import BookingService
from tests._maintenance import add_hours, add_workshop, make_session
from tests._user_vehicle import add_owner, add_vehicle


@pytest_asyncio.fixture
async def booking_api(monkeypatch):
    sessions = make_session()
    db = next(sessions)
    redis = FakeAsyncRedis()
    toolkit = RedisToolkit(redis, key_prefix="retry-api")
    user = add_owner(db)
    vehicle = add_vehicle(db, user)
    workshop = add_workshop(db)
    add_hours(db, workshop)
    service = BookingService(db, toolkit, SimpleTextLocationFinder(), config=BookingConfig())
    token = await service._issue_token(user, workshop.id, now_vn().date() + timedelta(days=3), time(9))
    body = {"confirmationToken": token, "userVehicleId": str(vehicle.id)}
    # Resolve ORM state before the independent request sessions start.
    user.user_id

    def request_service():
        with Session(db.get_bind()) as session:
            yield BookingService(session, toolkit, SimpleTextLocationFinder(), config=BookingConfig())

    monkeypatch.setitem(app.dependency_overrides, get_booking_service, request_service)
    monkeypatch.setitem(app.dependency_overrides, require_active_vehicle_owner, lambda: user)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, body, db
    await toolkit.pubsub.stop()
    await toolkit.cache.write_back_buffer.stop(final_flush=False)
    await redis.aclose()
    sessions.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent", [False, True])
async def test_same_http_request_returns_same_booking_after_retry(booking_api, concurrent):
    client, body, db = booking_api

    async def send():
        return await client.post("/api/v1/bookings", json=body, headers={"Idempotency-Key": "same-request"})

    first, second = await asyncio.gather(send(), send()) if concurrent else (await send(), await send())
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["bookingId"] == second.json()["data"]["bookingId"]
    assert len(db.exec(select(Booking)).all()) == 1


@pytest.mark.asyncio
async def test_changed_http_payload_with_same_key_returns_conflict(booking_api):
    client, body, _ = booking_api
    headers = {"Idempotency-Key": "same-request"}
    assert (await client.post("/api/v1/bookings", json=body, headers=headers)).status_code == 201
    response = await client.post("/api/v1/bookings", json={**body, "milestoneRef": "12000"}, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "status"), [("", 400), ("x" * 129, 400), ("x" * 128, 201)])
async def test_idempotency_key_length_bounds(booking_api, key, status):
    client, body, _ = booking_api
    response = await client.post("/api/v1/bookings", json=body, headers={"Idempotency-Key": key})
    assert response.status_code == status
