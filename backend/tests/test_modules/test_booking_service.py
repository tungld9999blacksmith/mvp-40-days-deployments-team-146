"""Regression tests for the app booking path (API-BK-02 → BK-03, ``create_hold``).

In-memory SQLite + fakeredis: the real slot lock and the real single-use
confirmation token run against a fake Redis.
"""

from __future__ import annotations

import hashlib
from datetime import time, timedelta

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from sqlmodel import select

from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.workshop import BookingConfirmationMode
from src.infrastructure.redis import RedisToolkit
from src.modules.booking import errors
from src.modules.booking.domain import BookingConfig, now_vn
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.booking.schemas import HoldRequest
from src.modules.booking.service import BookingService
from tests._maintenance import add_booking, add_hours, add_workshop, make_session
from tests._user_vehicle import add_owner, add_vehicle

SLOT = time(9)


@pytest.fixture
def session():
    yield from make_session()


@pytest_asyncio.fixture
async def toolkit():
    redis = FakeAsyncRedis()
    tk = RedisToolkit(redis, key_prefix="test", default_cache_ttl=60)
    yield tk
    await tk.pubsub.stop()
    await tk.cache.write_back_buffer.stop(final_flush=False)
    await redis.flushall()
    await redis.aclose()


@pytest.fixture
def day():
    return now_vn().date() + timedelta(days=3)


def _service(session, toolkit) -> BookingService:
    return BookingService(session, toolkit, SimpleTextLocationFinder(), config=BookingConfig())


async def _book(service, user, vehicle, workshop, day, slot=SLOT):
    availability = await service.check_availability(user, workshop.id, day, slot, with_alternatives=True)
    token = availability.requested.confirmation_token
    assert token is not None
    return await service.create_hold(user, HoldRequest(confirmation_token=token, user_vehicle_id=vehicle.id))


@pytest.mark.asyncio
async def test_second_open_booking_for_same_vehicle_is_rejected(session, toolkit, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    add_booking(session, user, vehicle, workshop, d=day, t=time(14), status=BookingStatus.CONFIRMED)

    with pytest.raises(errors.OpenBookingExistsError):
        await _book(_service(session, toolkit), user, vehicle, workshop, day)


@pytest.mark.asyncio
async def test_hold_waits_out_another_booking_in_flight_for_same_vehicle(session, toolkit, day):
    """BR-013 under a race: while another request for this vehicle (any slot) holds
    the vehicle lock, a second hold is refused instead of slipping past the count."""
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)

    async with toolkit.locks.transaction(f"booking:vehicle:{vehicle.id}", ttl=10):
        with pytest.raises(errors.OpenBookingExistsError):
            await _book(service, user, vehicle, workshop, day, time(9))

    assert session.exec(select(Booking).where(Booking.user_vehicle_id == vehicle.id)).all() == []


@pytest.mark.asyncio
async def test_full_slot_raises_slot_full_with_alternatives(session, toolkit, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session, total_technicians=1)
    add_hours(session, workshop)
    service = _service(session, toolkit)

    # The token is issued while the slot is still free...
    availability = await service.check_availability(user, workshop.id, day, SLOT, with_alternatives=True)
    token = availability.requested.confirmation_token
    # ...then another owner takes the only technician.
    other = add_owner(session, uid="uid-2", email="other@example.com")
    other_vehicle = add_vehicle(session, other, vin="RLLV00000000000B2", external_vehicle_id="VEH-2")
    add_booking(session, other, other_vehicle, workshop, d=day, t=SLOT, code="EVC-OTHER")

    with pytest.raises(errors.SlotFullError) as exc:
        await service.create_hold(user, HoldRequest(confirmation_token=token, user_vehicle_id=vehicle.id))
    assert exc.value.alternatives
    assert all(a.workshop_id == workshop.id for a in exc.value.alternatives)
    assert session.exec(select(Booking).where(Booking.user_vehicle_id == vehicle.id)).all() == []


@pytest.mark.asyncio
async def test_auto_workshop_confirms_immediately(session, toolkit, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session, mode=BookingConfirmationMode.AUTO)
    add_hours(session, workshop)

    out = await _book(_service(session, toolkit), user, vehicle, workshop, day)

    assert out.status == "CONFIRMED"
    assert out.booking_code is not None
    assert out.hold_expires_at is None


@pytest.mark.asyncio
async def test_open_slots_matches_check_availability_day_by_day(session, toolkit, day):
    """``open_slots`` (us-061, batched) applies the same BR-005/006 as ``check_availability``."""
    from src.common.core.workshop import WorkshopOperatingHour, WorkshopSlotBlock

    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session, total_technicians=2)
    add_hours(session, workshop, open_at=time(8), close_at=time(12))
    closed = session.exec(
        select(WorkshopOperatingHour).where(
            WorkshopOperatingHour.workshop_id == workshop.id,
            WorkshopOperatingHour.day_of_week == (day + timedelta(days=1)).isoweekday(),
        )
    ).one()
    closed.is_closed, closed.open_time, closed.close_time = True, None, None
    session.add(closed)
    other = add_owner(session, uid="uid-2", email="other@example.com")
    other_vehicle = add_vehicle(session, other, vin="RLLV00000000000B2", external_vehicle_id="VEH-2")
    add_booking(session, user, vehicle, workshop, d=day, t=time(9), code="EVC-A")
    add_booking(session, other, other_vehicle, workshop, d=day, t=time(9), code="EVC-B")
    add_booking(
        session, other, other_vehicle, workshop, d=day, t=time(10), code="EVC-C", status=BookingStatus.CANCELLED
    )
    session.add(WorkshopSlotBlock(workshop_id=workshop.id, block_date=day, time_slot=time(11), blocked_count=1))
    session.commit()
    service = _service(session, toolkit)

    batched = service.open_slots(workshop, day, day + timedelta(days=2))

    for d in (day, day + timedelta(days=2)):
        single = await service.check_availability(user, workshop.id, d, None, with_alternatives=False)
        assert batched[d] == single.slots
    assert day + timedelta(days=1) not in batched  # closed day
    assert [(s.time_slot, s.available, s.remaining) for s in batched[day]] == [
        (time(8), True, 2),
        (time(9), False, 0),
        (time(10), True, 2),
        (time(11), True, 1),
    ]


def test_region_match_ignores_accents_and_case(session):
    """BR-004: "Ha Noi" finds a workshop whose region is "Hà Nội"."""
    from src.modules.booking.domain import AnchorSource, LocationAnchor

    hanoi = add_workshop(session, name="VinFast Long Biên", region="Hà Nội")
    add_workshop(session, name="VinFast Sơn Trà", region="Đà Nẵng")
    finder = SimpleTextLocationFinder()
    workshops = list(session.exec(select(type(hanoi))).all())

    for needle in ("Ha Noi", "hà nội", "HA-NOI", "long bien"):
        ranked, _ = finder.rank(
            LocationAnchor(AnchorSource.SPECIFIED, province=needle), workshops, preferred_workshop_id=None, limit=5
        )
        assert [r.workshop.id for r in ranked] == [hanoi.id], needle


async def _hold_payload(service, user, vehicle, workshop, day):
    token = await service._issue_token(user, workshop.id, day, SLOT)
    return HoldRequest(confirmation_token=token, user_vehicle_id=vehicle.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [None, "retry-key"])
async def test_booking_retry_replays_durable_receipt_after_token_is_gone(session, toolkit, day, key):
    from src.common.core.maintenance.booking_request import BookingRequest

    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    first = await service.create_hold(user, payload, idempotency_key=key)
    assert not await toolkit.redis.exists(service._token_key(payload.confirmation_token))
    # New service, no response cache: recovery comes from the committed database.
    replay = await _service(session, toolkit).create_hold(user, payload, idempotency_key=key)
    assert replay.booking_id == first.booking_id
    assert len(session.exec(select(Booking)).all()) == 1
    assert len(session.exec(select(BookingRequest)).all()) == 1


@pytest.mark.asyncio
async def test_booking_rejects_reusing_key_for_changed_payload(session, toolkit, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    await service.create_hold(user, payload, idempotency_key="key")
    changed = payload.model_copy(update={"milestone_ref": "12000"})
    with pytest.raises(errors.IdempotencyConflictError):
        await service.create_hold(user, changed, idempotency_key="key")


@pytest.mark.asyncio
@pytest.mark.parametrize("after_commit", [False, True])
async def test_booking_recovers_from_database_failure_without_losing_token(
    session, toolkit, day, monkeypatch, after_commit
):
    from src.common.core.maintenance.booking_request import BookingRequest

    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    original = session.commit

    def fail_commit():
        if after_commit:
            original()
        raise RuntimeError("lost database connection")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        await service.create_hold(user, payload, idempotency_key="key")
    assert await toolkit.redis.exists(service._token_key(payload.confirmation_token))
    assert len(session.exec(select(BookingRequest)).all()) == int(after_commit)
    monkeypatch.setattr(session, "commit", original)
    result = await service.create_hold(user, payload, idempotency_key="key")
    assert result.status == "CONFIRMED"
    assert len(session.exec(select(Booking)).all()) == 1


@pytest.mark.asyncio
async def test_invalid_owner_cannot_consume_another_owners_token(session, toolkit, day):
    user = add_owner(session)
    other = add_owner(session, uid="other", email="other@example.com")
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    with pytest.raises(errors.InvalidConfirmationTokenError):
        await service.create_hold(other, payload)
    assert await toolkit.redis.exists(service._token_key(payload.confirmation_token))
    assert (await service.create_hold(user, payload)).status == "CONFIRMED"


@pytest.mark.asyncio
async def test_token_cannot_be_reused_under_another_key_after_cleanup_failure(session, toolkit, day, monkeypatch):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    original = toolkit.redis.delete

    async def fail_token_delete(*keys):
        if service._token_key(payload.confirmation_token) in keys:
            raise RuntimeError("redis unavailable during cleanup")
        return await original(*keys)

    monkeypatch.setattr(toolkit.redis, "delete", fail_token_delete)
    first = await service.create_hold(user, payload, idempotency_key="key")
    with pytest.raises(errors.IdempotencyConflictError):
        await service.create_hold(user, payload, idempotency_key="different-key")
    assert (await service.create_hold(user, payload, idempotency_key="key")).booking_id == first.booking_id


@pytest.mark.asyncio
async def test_availability_query_count_does_not_grow_with_number_of_slots(session, toolkit, day):
    from sqlalchemy import event

    user = add_owner(session)
    workshop = add_workshop(session)
    add_hours(session, workshop, open_at=time(0), close_at=time(23))
    service = _service(session, toolkit)
    workshop_id = workshop.id
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(session.bind, "before_cursor_execute", record)
    try:
        result = await service.check_availability(user, workshop_id, day, None, with_alternatives=False)
    finally:
        event.remove(session.bind, "before_cursor_execute", record)
    assert len(result.slots) >= 20
    assert len(statements) <= 4


@pytest.mark.asyncio
async def test_cancelled_request_keeps_booking_locks_until_commit_and_can_be_retried(
    session, toolkit, day, monkeypatch
):
    import asyncio
    from threading import Event

    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    entered, release = Event(), Event()
    original = service._create_booking_locked
    vehicle_lock = f"booking:vehicle:{vehicle.id}"
    slot_lock = f"booking:{workshop.id}:{day.isoformat()}:{SLOT.isoformat()}"

    def slow_commit(*args, **kwargs):
        entered.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_create_booking_locked", slow_commit)
    request = asyncio.create_task(service.create_hold(user, payload, idempotency_key="key"))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        request.cancel()
        await asyncio.sleep(0.02)
        assert not request.done()
        assert await toolkit.locks.is_locked(vehicle_lock)
        assert await toolkit.locks.is_locked(slot_lock)
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
    assert not await toolkit.locks.is_locked(vehicle_lock)
    replay = await service.create_hold(user, payload, idempotency_key="key")
    assert replay.status == "CONFIRMED"
    assert len(session.exec(select(Booking)).all()) == 1


@pytest.mark.asyncio
async def test_second_cancellation_still_waits_for_the_booking_write(session, toolkit, day, monkeypatch):
    import asyncio
    from threading import Event

    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    entered, release = Event(), Event()
    original = service._create_booking_locked
    slot_lock = f"booking:{workshop.id}:{day.isoformat()}:{SLOT.isoformat()}"

    def slow_commit(*args, **kwargs):
        entered.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_create_booking_locked", slow_commit)
    request = asyncio.create_task(service.create_hold(user, payload, idempotency_key="key"))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        request.cancel()
        await asyncio.sleep(0.02)
        request.cancel()  # e.g. the chat deadline, then the client disconnecting
        await asyncio.sleep(0.02)
        assert not request.done()
        assert await toolkit.locks.is_locked(slot_lock)
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
    assert not await toolkit.locks.is_locked(slot_lock)
    assert len(session.exec(select(Booking)).all()) == 1


@pytest.mark.asyncio
async def test_cancelled_request_whose_write_fails_rolls_back_and_allows_retry(session, toolkit, day, monkeypatch):
    import asyncio
    from threading import Event

    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    entered, release = Event(), Event()

    def failing_commit(user_, vehicle_, workshop_, d, t, **kwargs):
        entered.set()
        release.wait(3)
        # Leave real uncommitted work behind, as a connection lost mid-commit would.
        session.add(
            Booking(
                booking_code="EVC-FAIL",
                user_id=user_.user_id,
                user_vehicle_id=vehicle_.id,
                workshop_id=workshop_.id,
                booking_date=d,
                time_slot=t,
                status=BookingStatus.PENDING,
            )
        )
        session.flush()
        raise RuntimeError("database gone")

    monkeypatch.setattr(service, "_create_booking_locked", failing_commit)
    request = asyncio.create_task(service.create_hold(user, payload, idempotency_key="key"))
    assert await asyncio.to_thread(entered.wait, 2)
    request.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert not session.exec(select(Booking)).all()
    assert await toolkit.redis.exists(service._token_key(payload.confirmation_token))
    monkeypatch.undo()
    assert (await service.create_hold(user, payload, idempotency_key="key")).status == "CONFIRMED"


@pytest.mark.asyncio
async def test_contended_request_lock_returns_service_unavailable_without_booking(session, toolkit, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    service = _service(session, toolkit)
    payload = await _hold_payload(service, user, vehicle, workshop, day)
    token_hash = hashlib.sha256(payload.confirmation_token.encode()).hexdigest()

    async with toolkit.locks.transaction(f"booking:token:{token_hash}", ttl=30):
        with pytest.raises(errors.ServiceUnavailableError):
            await service.create_hold(user, payload, idempotency_key="key")
    assert not session.exec(select(Booking)).all()
    assert await toolkit.redis.exists(service._token_key(payload.confirmation_token))


async def _reschedulable(session, toolkit, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    booking = add_booking(session, user, vehicle, workshop, d=day, t=SLOT, status=BookingStatus.CONFIRMED)
    service = _service(session, toolkit)
    new_slot = time(10)
    token = await service._issue_token(user, workshop.id, day, new_slot, rescheduling=booking)
    return service, user, workshop, booking, token, new_slot


@pytest.mark.asyncio
async def test_reschedule_moves_the_booking_and_keeps_id_and_code(session, toolkit, day):
    service, user, _, booking, token, new_slot = await _reschedulable(session, toolkit, day)
    booking_id, code = booking.id, booking.booking_code

    moved = await service.reschedule(user, booking_id, token)

    assert (moved.id, moved.booking_code, moved.time_slot) == (booking_id, code, new_slot)


@pytest.mark.asyncio
async def test_cancelled_reschedule_keeps_slot_locks_until_the_write_finishes(session, toolkit, day, monkeypatch):
    import asyncio
    from threading import Event

    service, user, workshop, booking, token, new_slot = await _reschedulable(session, toolkit, day)
    booking_id = booking.id
    entered, release = Event(), Event()
    original = service._reschedule_locked
    locks = [f"booking:{workshop.id}:{day.isoformat()}:{t.isoformat()}" for t in (SLOT, new_slot)]

    def slow_write(*args, **kwargs):
        entered.set()
        release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_reschedule_locked", slow_write)
    request = asyncio.create_task(service.reschedule(user, booking_id, token))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        request.cancel()
        await asyncio.sleep(0.02)
        assert not request.done()
        assert all([await toolkit.locks.is_locked(name) for name in locks])
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
    assert not any([await toolkit.locks.is_locked(name) for name in locks])
    session.expire_all()
    assert session.get(Booking, booking_id).time_slot == new_slot  # moved exactly once


@pytest.mark.asyncio
async def test_contended_reschedule_slot_returns_service_unavailable(session, toolkit, day):
    service, user, workshop, booking, token, new_slot = await _reschedulable(session, toolkit, day)
    booking_id = booking.id

    async with toolkit.locks.transaction(f"booking:{workshop.id}:{day.isoformat()}:{new_slot.isoformat()}", ttl=30):
        with pytest.raises(errors.ServiceUnavailableError):
            await service.reschedule(user, booking_id, token)
    session.expire_all()
    assert session.get(Booking, booking_id).time_slot == SLOT
