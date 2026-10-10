"""API-level tests for the derived in-app notification feed (API-NOTI-003)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.maintenance.booking import BookingStatus
from src.common.core.maintenance.booking_status_event import BookingActorType, BookingStatusEvent
from src.common.core.maintenance.quote import Quote, QuoteStatus
from src.common.core.maintenance.reminder import Reminder, ReminderChannel, ReminderLevel
from src.common.core.notification import BookingReminder
from src.common.core.notification.event_delivery import BookingReminderStatus
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


def _reviewed_quote(session, vehicle, workshop, owner, *, status, at, seen=False):
    quote = Quote(
        user_vehicle_id=vehicle.id,
        workshop_id=workshop.id,
        odo_milestone=12_000,
        status=status,
        estimated_total=Decimal("1500000"),
        approved_total=Decimal("1400000") if status == QuoteStatus.APPROVED else None,
        submitted_at=at - timedelta(hours=2),
        reviewed_at=at,
        reviewed_by=owner.id,
        expires_at=at + timedelta(days=7) if status == QuoteStatus.APPROVED else None,
        result_seen_at=at + timedelta(hours=1) if seen else None,
        reviewer_note=None if status == QuoteStatus.APPROVED else "Xe cần kiểm tra pin trước.",
    )
    session.add(quote)
    return quote


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
    quote = _reviewed_quote(
        session, vehicle, workshop, ws_owner, status=QuoteStatus.APPROVED, at=NOW - timedelta(days=3)
    )
    _reviewed_quote(
        session, vehicle, workshop, ws_owner, status=QuoteStatus.REJECTED, at=NOW - timedelta(days=4), seen=True
    )
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
        "QUOTE_RESULT",
        "QUOTE_RESULT",
        "MAINTENANCE_REMINDER",
    ]
    follow_up, booking_update, approved, rejected, reminder = data["items"]
    assert follow_up["unread"] is True and follow_up["followUp"]["workshopName"] == "VinFast Smart City"
    assert booking_update["booking"]["bookingCode"] == "EVC-7K2M"
    assert booking_update["booking"]["status"] == "CONFIRMED"
    assert booking_update["unread"] is False and reminder["unread"] is False
    assert approved["quote"]["quoteId"] == str(quote.id)
    assert approved["quote"]["status"] == "APPROVED" and approved["unread"] is True
    assert rejected["quote"]["status"] == "REJECTED" and rejected["unread"] is False
    assert reminder["reminder"] == {
        "userVehicleId": str(vehicle.id),
        "level": "WARNING",
        "odoMilestoneKm": 12_000,
        "resolved": False,
        "resolutionReason": None,
    }
    assert data["unreadCount"] == 2


def _booking_reminder(session, booking, *, status, scheduled_at, appointment_at, sent_at=None):
    session.add(
        BookingReminder(
            booking_id=booking.id,
            appointment_at=appointment_at,
            scheduled_at=scheduled_at,
            status=status,
            sent_at=sent_at,
            skip_reason="TOO_LATE" if status == BookingReminderStatus.SKIPPED else None,
        )
    )


@pytest.mark.asyncio
async def test_feed_lists_processed_appointment_reminders(api):
    """us-069 BR-1707: the in-app feed is the default channel, so a reminder the job
    processed shows up even when no external channel succeeded; skipped ones do not."""
    client, session = api
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session, name="VinFast Smart City")
    tomorrow = NOW + timedelta(hours=20)
    upcoming = add_booking(session, user, vehicle, workshop, d=tomorrow.date(), code="EVC-SOON")
    done = add_booking(
        session, user, vehicle, workshop, d=date(2026, 9, 20), code="EVC-DONE", status=BookingStatus.COMPLETED
    )
    skipped = add_booking(session, user, vehicle, workshop, d=date(2026, 9, 25), code="EVC-SKIP")

    # No external channel enabled: the job settles it as ``failed`` without ``sent_at``.
    _booking_reminder(
        session,
        upcoming,
        status=BookingReminderStatus.FAILED,
        scheduled_at=NOW - timedelta(hours=4),
        appointment_at=tomorrow,
    )
    _booking_reminder(
        session,
        done,
        status=BookingReminderStatus.SENT,
        scheduled_at=NOW - timedelta(days=10, hours=1),
        sent_at=NOW - timedelta(days=10),
        appointment_at=NOW - timedelta(days=9),
    )
    _booking_reminder(
        session,
        skipped,
        status=BookingReminderStatus.SKIPPED,
        scheduled_at=NOW - timedelta(days=5),
        appointment_at=NOW - timedelta(days=4),
    )
    session.commit()

    r = await client.get(URL, headers=AUTH)

    assert r.status_code == 200
    data = r.json()["data"]
    assert [item["kind"] for item in data["items"]] == ["BOOKING_REMINDER", "BOOKING_REMINDER"]
    soon, past = data["items"]
    assert soon["bookingReminder"]["bookingCode"] == "EVC-SOON"
    assert soon["bookingReminder"]["workshopName"] == "VinFast Smart City"
    assert soon["unread"] is True  # confirmed, attendance not confirmed, appointment ahead
    assert past["bookingReminder"]["bookingCode"] == "EVC-DONE" and past["unread"] is False
    assert data["unreadCount"] == 1

    upcoming.attendance_confirmed_at = NOW
    session.add(upcoming)
    session.commit()
    again = (await client.get(URL, headers=AUTH)).json()["data"]
    assert again["unreadCount"] == 0


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
