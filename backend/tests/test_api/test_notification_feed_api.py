"""API-level tests for the derived in-app notification feed (API-NOTI-003)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.maintenance.booking import BookingStatus
from src.common.core.maintenance.booking_status_event import BookingActorType, BookingStatusEvent
from src.common.core.maintenance.reminder import Reminder, ReminderChannel, ReminderLevel
from src.infrastructure.supabase.db import get_session
from src.main import app
from src.modules.oauth.dependency import verify_firebase_token
from tests._maintenance import add_booking, add_workshop, add_workshop_owner, make_session
from tests._user_vehicle import add_owner, add_vehicle

URL = "/api/v1/notifications"
AUTH = {"Authorization": "Bearer x"}
NOW = datetime.now(UTC)


@pytest_asyncio.fixture
async def api():
    session = next(make_session())
    claims = {"uid": "uid-1"}

    def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[verify_firebase_token] = lambda: claims
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session
    app.dependency_overrides.clear()
    session.close()


def _reminder(session, vehicle, *, at, level=ReminderLevel.WARNING):
    session.add(
        Reminder(
            user_vehicle_id=vehicle.id,
            target_odo_milestone=12_000,
            reminder_level=level,
            channel=ReminderChannel.IN_APP,
            scheduled_at=at,
        )
    )


def _event(session, booking, *, to, actor, at, reason=None):
    session.add(
        BookingStatusEvent(
            booking_id=booking.id,
            from_status=BookingStatus.PENDING,
            to_status=to,
            actor_type=actor,
            source="BOARD",
            reason_code=reason,
            created_at=at,
        )
    )


@pytest.mark.asyncio
async def test_feed_merges_sources_newest_first_with_unread_count(api):
    client, session = api
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    ws_owner = add_workshop_owner(session, uid="ws-owner")
    workshop = add_workshop(session, name="VinFast Smart City", owner=ws_owner)
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 4), t=time(14), code="EVC-7K2M")

    _reminder(session, vehicle, at=NOW - timedelta(days=5))
    _event(
        session, booking, to=BookingStatus.CONFIRMED, actor=BookingActorType.WORKSHOP_OWNER, at=NOW - timedelta(days=2)
    )
    session.add(
        FollowUp(
            booking_id=booking.id,
            message="Anh/chị hài lòng với lần bảo dưỡng chứ?",
            status=FollowUpStatus.SENT,
            scheduled_at=NOW - timedelta(days=1, hours=1),
            sent_at=NOW - timedelta(days=1),
        )
    )
    session.commit()

    r = await client.get(URL, headers=AUTH)

    assert r.status_code == 200
    data = r.json()["data"]
    assert [item["kind"] for item in data["items"]] == [
        "FOLLOW_UP",
        "BOOKING_UPDATE",
        "MAINTENANCE_REMINDER",
    ]
    follow_up, booking_update, reminder = data["items"]
    assert follow_up["unread"] is True and follow_up["followUp"]["workshopName"] == "VinFast Smart City"
    assert booking_update["booking"]["bookingCode"] == "EVC-7K2M"
    assert booking_update["booking"]["status"] == "CONFIRMED"
    assert booking_update["unread"] is False and reminder["unread"] is False
    assert reminder["reminder"] == {
        "userVehicleId": str(vehicle.id),
        "level": "WARNING",
        "odoMilestoneKm": 12_000,
        "resolved": False,
    }
    assert data["unreadCount"] == 1


@pytest.mark.asyncio
async def test_feed_skips_own_actions_old_entries_and_other_owners(api):
    client, session = api
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    other = add_owner(session, uid="uid-2", email="other@example.com")
    other_vehicle = add_vehicle(session, other, vin="RLLV00000000000B2", external_vehicle_id="VEH-2")
    ws_owner = add_workshop_owner(session, uid="ws-owner")
    workshop = add_workshop(session, owner=ws_owner)
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 4), code="EVC-OWN")

    # The owner cancelled it themselves: not news to them.
    _event(
        session,
        booking,
        to=BookingStatus.CANCELLED,
        actor=BookingActorType.VEHICLE_OWNER,
        at=NOW,
        reason="CHANGE_OF_PLANS",
    )
    _reminder(session, vehicle, at=NOW - timedelta(days=120))  # outside the 90-day window
    _reminder(session, other_vehicle, at=NOW - timedelta(days=1))  # someone else's vehicle
    session.commit()

    r = await client.get(URL, headers=AUTH)

    assert r.status_code == 200
    assert r.json()["data"] == {"items": [], "unreadCount": 0}


@pytest.mark.asyncio
async def test_feed_requires_a_vehicle_owner(api):
    client, session = api
    add_workshop_owner(session, uid="uid-1")  # signed in as a workshop owner, not a vehicle owner

    r = await client.get(URL, headers=AUTH)

    assert r.status_code == 403
