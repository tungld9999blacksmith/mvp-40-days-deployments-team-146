"""Real booking service/Redis locks with fake Redis; attribution counts confirmations."""

from datetime import UTC, datetime, time, timedelta

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from sqlmodel import select

from src.common.core.maintenance import Booking, BookingStatus, Reminder
from src.common.core.maintenance.booking import PricingFlow
from src.common.core.maintenance.booking_line import BookingLine
from src.common.core.maintenance.reminder import ReminderChannel, ReminderLevel
from src.common.core.notification import ReminderBookingAttribution
from src.common.core.workshop import BookingConfirmationMode
from src.infrastructure.redis import RedisToolkit
from src.modules.booking.errors import BookingError
from src.modules.booking.schemas import HoldRequest
from src.modules.booking.state_machine import Actor, BookingStateMachine
from src.modules.notification.booking_attribution import confirm_booking_origin
from src.modules.notification.metrics_service import aggregate_metrics
from tests._maintenance import add_hours, add_workshop, make_session
from tests._user_vehicle import add_owner, add_rules, add_vehicle
from tests.test_modules.test_booking_service import _redis_calls_in_transaction, _service


@pytest.fixture
def db():
    yield from make_session()


@pytest_asyncio.fixture
async def toolkit():
    redis = FakeAsyncRedis()
    toolkit = RedisToolkit(redis, key_prefix="usage-test", default_cache_ttl=60)
    yield toolkit
    await toolkit.pubsub.stop()
    await toolkit.cache.write_back_buffer.stop(final_flush=False)
    await redis.aclose()


def setup(db, *, mode=BookingConfirmationMode.MANUAL):
    owner = add_owner(db)
    vehicle = add_vehicle(db, owner)
    workshop = add_workshop(db, mode=mode)
    add_hours(db, workshop)
    now = datetime.now(UTC)
    reminder = Reminder(
        user_vehicle_id=vehicle.id,
        target_odo_milestone=12000,
        reminder_level=ReminderLevel.EARLY,
        channel=ReminderChannel.IN_APP,
        scheduled_at=now - timedelta(days=1),
    )
    db.add(reminder)
    db.commit()
    return owner, vehicle, workshop, reminder, now


async def payload(service, owner, vehicle, workshop, now, reminder_id=None):
    availability = await service.check_availability(
        owner, workshop.id, now.date() + timedelta(days=3), time(9), with_alternatives=True
    )
    return HoldRequest(
        confirmation_token=availability.requested.confirmation_token,
        user_vehicle_id=vehicle.id,
        milestone_ref="12000",
        source_reminder_id=reminder_id,
    )


@pytest.mark.asyncio
async def test_selected_package_keeps_direct_reminder_origin_without_transaction_over_redis(db, toolkit, monkeypatch):
    owner, vehicle, workshop, reminder, now = setup(db, mode=BookingConfirmationMode.AUTO)
    add_rules(db)
    owner_id, vehicle_id, workshop_id, reminder_id = owner.user_id, vehicle.id, workshop.id, reminder.id
    service = _service(db, toolkit)
    redis_calls = _redis_calls_in_transaction(db, toolkit, monkeypatch)

    created = await service.create_for_slot(
        owner,
        vehicle_id,
        workshop_id,
        now.date() + timedelta(days=3),
        time(9),
        source="CHAT",
        odo_milestone=12000,
        source_reminder_id=reminder_id,
        maintenance_package_code="BALANCED",
        selected_item_codes={"BRAKE_INSPECTION"},
    )

    assert redis_calls == []
    booking = db.get(Booking, created.booking_id)
    assert booking.user_id == owner_id
    assert booking.pricing_flow == PricingFlow.TWO_TIER
    assert created.maintenance_package_code == booking.maintenance_package_code == "BALANCED"
    lines = db.exec(select(BookingLine).where(BookingLine.booking_id == booking.id)).all()
    assert {line.item_code for line in lines} == {"BRAKE_INSPECTION"}
    attribution = db.get(ReminderBookingAttribution, booking.id)
    assert attribution.reminder_id == reminder_id and attribution.match_method == "DIRECT"
    assert attribution.confirmed_at is not None


@pytest.mark.asyncio
async def test_hold_not_counted_until_real_confirmation_and_confirmation_is_idempotent(db, toolkit):
    owner, vehicle, workshop, reminder, now = setup(db)
    service = _service(db, toolkit)
    request = await payload(service, owner, vehicle, workshop, now, reminder.id)
    created = await service.create_hold(owner, request, idempotency_key="same-confirm")
    replay = await service.create_hold(owner, request, idempotency_key="same-confirm")
    assert replay.booking_id == created.booking_id
    assert db.exec(select(ReminderBookingAttribution)).one().confirmed_at is None
    assert aggregate_metrics(db, now=now + timedelta(minutes=1))["confirmedBookings"] == 0
    booking = db.get(Booking, created.booking_id)
    BookingStateMachine(db).transition(booking, BookingStatus.CONFIRMED, actor=Actor.system(), source="TEST")
    db.commit()
    confirmed_at = db.exec(select(ReminderBookingAttribution)).one().confirmed_at
    confirm_booking_origin(db, booking, now + timedelta(minutes=1))
    db.commit()
    assert db.exec(select(ReminderBookingAttribution)).one().confirmed_at == confirmed_at
    report = aggregate_metrics(db, now=now + timedelta(minutes=1))
    assert report["directConfirmedBookings"] == 1


@pytest.mark.asyncio
async def test_auto_confirm_matches_recent_reminder_without_claiming_direct_click(db, toolkit):
    owner, vehicle, workshop, reminder, now = setup(db, mode=BookingConfirmationMode.AUTO)
    service = _service(db, toolkit)
    created = await service.create_hold(owner, await payload(service, owner, vehicle, workshop, now))
    assert created.status == "CONFIRMED"
    assert db.exec(select(ReminderBookingAttribution)).one().match_method == "RECENT_REMINDER"
    assert aggregate_metrics(db, now=now + timedelta(minutes=1))["recentReminderConfirmedBookings"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_origin", ["foreign", "wrong_milestone"])
async def test_foreign_or_wrong_milestone_origin_never_attaches_to_booking(db, toolkit, invalid_origin):
    owner, vehicle, workshop, reminder, now = setup(db)
    other = add_owner(db, uid="other", email="other@example.com")
    other_vehicle = add_vehicle(db, other, vin="RLLV00000000000B2", external_vehicle_id="OTHER")
    if invalid_origin == "foreign":
        reminder.user_vehicle_id = other_vehicle.id
    else:
        reminder.target_odo_milestone = 24000
    db.add(reminder)
    db.commit()
    service = _service(db, toolkit)
    with pytest.raises(BookingError) as rejected:
        await service.create_hold(owner, await payload(service, owner, vehicle, workshop, now, reminder.id))
    assert rejected.value.code == "INVALID_REMINDER_CONTEXT"
    assert db.exec(select(Booking)).all() == []
    assert db.exec(select(ReminderBookingAttribution)).all() == []


@pytest.mark.asyncio
async def test_expired_reminder_does_not_count_as_recent_conversion(db, toolkit):
    owner, vehicle, workshop, reminder, now = setup(db, mode=BookingConfirmationMode.AUTO)
    reminder.scheduled_at = now - timedelta(days=8)
    db.add(reminder)
    db.commit()
    service = _service(db, toolkit)
    await service.create_hold(owner, await payload(service, owner, vehicle, workshop, now, reminder.id))
    assert db.exec(select(ReminderBookingAttribution)).all() == []


@pytest.mark.asyncio
async def test_booking_created_in_window_still_counts_when_workshop_confirms_later(db, toolkit):
    owner, vehicle, workshop, reminder, now = setup(db)
    service = _service(db, toolkit)
    created = await service.create_hold(owner, await payload(service, owner, vehicle, workshop, now, reminder.id))
    booking = db.get(Booking, created.booking_id)
    confirm_booking_origin(db, booking, now)
    assert db.exec(select(ReminderBookingAttribution)).one().confirmed_at is None
    booking.status = BookingStatus.CONFIRMED
    db.add(booking)
    db.commit()
    confirm_booking_origin(db, booking, now + timedelta(days=10))
    db.commit()
    assert db.exec(select(ReminderBookingAttribution)).one().confirmed_at is not None
    # Reports before the confirmation time must not include a future event.
    assert aggregate_metrics(db, now=now)["confirmedBookings"] == 0
