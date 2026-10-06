"""Slow database/broker work must not prevent unrelated HTTP requests."""

import asyncio
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from src.main import app
from src.modules.booking import schemas as booking_schemas
from src.modules.booking.dependency import get_ticket_service
from src.modules.booking.dependency import require_active_vehicle_owner as require_booking_owner
from src.modules.cost_estimate import schemas as estimate_schemas
from src.modules.cost_estimate.dependency import get_cost_estimation_service, get_estimable_vehicle
from src.modules.notification import schemas as notification_schemas
from src.modules.notification.dependency import get_notification_feed_service
from src.modules.oem_integration.service import OemWebhookService
from src.modules.user_vehicle.dependency import get_user_vehicle_service, require_active_vehicle_owner
from tests._user_vehicle import NOW, MemoryEventStore, RecordingScheduler
from tests.test_modules.test_oem_integration_service import _event, _signed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/user-vehicles",
        "/api/v1/bookings",
        "/api/v1/notifications",
        f"/api/v1/user-vehicles/{uuid4()}/maintenance-milestones",
    ],
)
async def test_health_responds_while_owner_page_waits_for_database(path):
    entered, release = Event(), Event()

    def slow_read(*args, **kwargs):
        entered.set()
        release.wait(3)
        if path.endswith("user-vehicles"):
            return []
        if path.endswith("notifications"):
            return notification_schemas.NotificationFeedOut(items=[], unread_count=0)
        if path.endswith("maintenance-milestones"):
            return estimate_schemas.MilestonesData(model_id=None, next_odo_milestone=None, milestones=[])
        return booking_schemas.MyBookingsData(items=[])

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_active_vehicle_owner] = lambda: SimpleNamespace(user_id=1)
    app.dependency_overrides[require_booking_owner] = lambda: SimpleNamespace(user_id=1)
    app.dependency_overrides[get_user_vehicle_service] = lambda: SimpleNamespace(list_vehicles=slow_read)
    app.dependency_overrides[get_ticket_service] = lambda: SimpleNamespace(list_for_user=slow_read)
    app.dependency_overrides[get_estimable_vehicle] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_cost_estimation_service] = lambda: SimpleNamespace(list_milestones=slow_read)
    app.dependency_overrides[get_notification_feed_service] = lambda: SimpleNamespace(list_for_user=slow_read)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            request = asyncio.create_task(client.get(path))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                health = await asyncio.wait_for(client.get("/health"), timeout=1)
                assert health.status_code == 200
                assert not request.done(), "The page blocked the event loop until its database read finished"
            finally:
                release.set()
                response = await request
            assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
@pytest.mark.parametrize("slow_stage", ["database", "broker"])
async def test_webhook_does_not_block_health(slow_stage):
    entered, release = Event(), Event()
    vehicle_id = uuid4()

    def slow_work(*args, **kwargs):
        entered.set()
        release.wait(3)
        return vehicle_id

    scheduler = RecordingScheduler()
    service = OemWebhookService(None, scheduler, MemoryEventStore(), secret="test-secret", clock=lambda: NOW)
    service._find_vehicle_id = slow_work if slow_stage == "database" else lambda _: vehicle_id
    if slow_stage == "broker":
        scheduler.schedule = slow_work

    request = asyncio.create_task(service.handle(**_signed(_event())))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await asyncio.wait_for(client.get("/health"), timeout=1)
        assert response.status_code == 200
        assert not request.done(), "Webhook I/O blocked the event loop"
    finally:
        release.set()
        result = await request
    assert result.accepted
