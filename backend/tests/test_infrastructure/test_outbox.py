"""Transactional outbox: publish in the caller's transaction, dispatch to typed handlers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from src.infrastructure.outbox import (
    DispatcherConfig,
    DuplicateHandlerError,
    OutboxContext,
    OutboxDispatcher,
    OutboxEvent,
    OutboxEventRecord,
    OutboxHandler,
    OutboxPublisher,
    OutboxRegistry,
    OutboxStatus,
    PermanentError,
    RetryableError,
)

T0 = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


class BookingConfirmed(OutboxEvent):
    event_type = "test.booking_confirmed"
    booking_id: UUID
    note: str = ""


class RecordingHandler(OutboxHandler[BookingConfirmed]):
    event = BookingConfirmed

    def __init__(self, fail_with: BaseException | None = None) -> None:
        self.calls: list[tuple[BookingConfirmed, OutboxContext]] = []
        self.fail_with = fail_with

    async def handle(self, event: BookingConfirmed, ctx: OutboxContext) -> None:
        self.calls.append((event, ctx))
        if self.fail_with is not None:
            raise self.fail_with


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[OutboxEventRecord.__table__])
    return engine


@pytest.fixture
def clock():
    return Clock()


def _dispatcher(engine, registry, clock, **config) -> OutboxDispatcher:
    cfg = DispatcherConfig(**{"backoff_base_seconds": 10, "backoff_max_seconds": 100, **config})
    # jitter = 1.0 → the backoff is exactly the ceiling.
    return OutboxDispatcher(engine, registry, cfg, clock=clock, jitter=lambda: 1.0, worker_id="test")


def _publish(engine, clock, event=None, **kwargs) -> UUID:
    with Session(engine) as session:
        record = OutboxPublisher(clock=clock).publish(session, event or BookingConfirmed(booking_id=uuid4()), **kwargs)
        session.commit()
        return record.id


def _row(engine, event_id) -> OutboxEventRecord:
    with Session(engine) as session:
        return session.get(OutboxEventRecord, event_id)


def _registry(handler) -> OutboxRegistry:
    registry = OutboxRegistry()
    registry.register(handler)
    return registry


# ── publish ──────────────────────────────────────────────────────────────


def test_publish_is_part_of_the_caller_transaction(engine, clock):
    publisher = OutboxPublisher(clock=clock)
    with Session(engine) as session:
        publisher.publish(session, BookingConfirmed(booking_id=uuid4()))
        session.rollback()
    with Session(engine) as session:
        assert session.exec(select(OutboxEventRecord)).all() == []

    booking_id = uuid4()
    with Session(engine) as session:
        publisher.publish(
            session, BookingConfirmed(booking_id=booking_id, note="hi"), aggregate_type="booking", aggregate_id="b-1"
        )
        session.commit()
    with Session(engine) as session:
        (row,) = session.exec(select(OutboxEventRecord)).all()
    assert row.event_type == "test.booking_confirmed"
    assert row.payload == {"booking_id": str(booking_id), "note": "hi"}
    assert (row.status, row.attempts, row.schema_version) == (OutboxStatus.PENDING, 0, 1)
    assert (row.aggregate_type, row.aggregate_id) == ("booking", "b-1")


def test_wakeup_fires_once_after_commit_and_never_on_rollback(engine, clock):
    calls = []
    publisher = OutboxPublisher(wakeup=lambda: calls.append(1), clock=clock)

    with Session(engine) as session:
        publisher.publish(session, BookingConfirmed(booking_id=uuid4()))
        session.rollback()
    assert calls == []

    with Session(engine) as session:
        publisher.publish(session, BookingConfirmed(booking_id=uuid4()))
        publisher.publish(session, BookingConfirmed(booking_id=uuid4()))
        assert calls == []  # not before the commit
        session.commit()
        assert calls == [1]  # one wakeup per commit, not per event
        session.commit()
        assert calls == [1]


def test_failed_wakeup_does_not_break_the_commit(engine, clock):
    def broken():
        raise ConnectionError("redis down")

    with Session(engine) as session:
        OutboxPublisher(wakeup=broken, clock=clock).publish(session, BookingConfirmed(booking_id=uuid4()))
        session.commit()
    with Session(engine) as session:
        assert len(session.exec(select(OutboxEventRecord)).all()) == 1


def test_delayed_event_skips_the_wakeup_and_waits_until_due(engine, clock):
    calls = []
    handler = RecordingHandler()
    with Session(engine) as session:
        OutboxPublisher(wakeup=lambda: calls.append(1), clock=clock).publish(
            session, BookingConfirmed(booking_id=uuid4()), delay=timedelta(minutes=5)
        )
        session.commit()
    assert calls == []

    dispatcher = _dispatcher(engine, _registry(handler), clock)
    assert asyncio.run(dispatcher.run_once()).claimed == 0
    clock.advance(minutes=5)
    assert asyncio.run(dispatcher.run_once()).succeeded == 1


def test_dedup_key_returns_the_existing_event(engine, clock):
    first = _publish(engine, clock, dedup_key="booking:1:confirmed")
    second = _publish(engine, clock, dedup_key="booking:1:confirmed")
    assert first == second
    with Session(engine) as session:
        assert len(session.exec(select(OutboxEventRecord)).all()) == 1


# ── registry ─────────────────────────────────────────────────────────────


def test_registry_rejects_a_second_handler_for_the_same_event_type():
    registry = _registry(RecordingHandler())
    with pytest.raises(DuplicateHandlerError):
        registry.register(RecordingHandler())
    assert registry.event_types() == ["test.booking_confirmed"]


def test_registry_rejects_a_handler_without_an_event_class():
    class Broken(OutboxHandler):
        async def handle(self, event, ctx):
            return None

    with pytest.raises(TypeError):
        OutboxRegistry().register(Broken())


# ── dispatch ─────────────────────────────────────────────────────────────


def test_dispatch_deserializes_the_event_and_marks_it_succeeded(engine, clock):
    booking_id = uuid4()
    event_id = _publish(engine, clock, BookingConfirmed(booking_id=booking_id), aggregate_type="booking")
    handler = RecordingHandler()

    report = asyncio.run(_dispatcher(engine, _registry(handler), clock).run_once())

    assert report.as_dict() == {"claimed": 1, "succeeded": 1, "retried": 0, "dead": 0, "lost": 0}
    ((event, ctx),) = handler.calls
    assert event == BookingConfirmed(booking_id=booking_id)
    assert (ctx.event_id, ctx.attempt, ctx.max_attempts, ctx.aggregate_type) == (event_id, 1, 10, "booking")
    row = _row(engine, event_id)
    assert row.status == OutboxStatus.SUCCEEDED
    assert row.processed_at is not None
    assert (row.claim_token, row.locked_until, row.last_error) == (None, None, None)


def test_dispatch_handles_events_oldest_first_up_to_the_batch_size(engine, clock):
    ids = []
    for minute in range(3):
        ids.append(_publish(engine, clock, BookingConfirmed(booking_id=uuid4(), note=str(minute))))
        clock.advance(minutes=1)
    handler = RecordingHandler()

    report = asyncio.run(_dispatcher(engine, _registry(handler), clock, batch_size=2).run_once())

    assert report.succeeded == 2
    assert [event.note for event, _ in handler.calls] == ["0", "1"]
    assert _row(engine, ids[2]).status == OutboxStatus.PENDING


def test_handler_failure_retries_with_exponential_backoff_then_goes_dead(engine, clock):
    event_id = _publish(engine, clock, max_attempts=3)
    handler = RecordingHandler(fail_with=RuntimeError("smtp timeout"))
    dispatcher = _dispatcher(engine, _registry(handler), clock)

    assert asyncio.run(dispatcher.run_once()).retried == 1
    row = _row(engine, event_id)
    assert (row.status, row.attempts, row.last_error) == (OutboxStatus.PENDING, 1, "RuntimeError")
    assert row.available_at.replace(tzinfo=UTC) == T0 + timedelta(seconds=10)

    assert asyncio.run(dispatcher.run_once()).claimed == 0  # not due yet
    clock.advance(seconds=10)
    assert asyncio.run(dispatcher.run_once()).retried == 1
    assert _row(engine, event_id).available_at.replace(tzinfo=UTC) == clock.now + timedelta(seconds=20)

    clock.advance(seconds=20)
    assert asyncio.run(dispatcher.run_once()).dead == 1
    row = _row(engine, event_id)
    assert (row.status, row.attempts) == (OutboxStatus.DEAD, 3)
    assert [ctx.attempt for _, ctx in handler.calls] == [1, 2, 3]
    assert handler.calls[-1][1].is_last_attempt


def test_backoff_is_capped_and_jittered(engine, clock):
    dispatcher = OutboxDispatcher(
        engine,
        OutboxRegistry(),
        DispatcherConfig(backoff_base_seconds=10, backoff_max_seconds=100),
        jitter=lambda: 0.0,
    )
    assert dispatcher.backoff_seconds(1) == 5  # 50 % of the 10 s ceiling
    assert dispatcher.backoff_seconds(10) == 50  # capped at 100, then 50 %


def test_retryable_error_can_set_its_own_delay(engine, clock):
    event_id = _publish(engine, clock)
    handler = RecordingHandler(fail_with=RetryableError("rate limited", retry_after=60))
    asyncio.run(_dispatcher(engine, _registry(handler), clock).run_once())
    row = _row(engine, event_id)
    assert row.last_error == "RetryableError"
    assert row.available_at.replace(tzinfo=UTC) == T0 + timedelta(seconds=60)


def test_permanent_error_goes_dead_without_retry(engine, clock):
    event_id = _publish(engine, clock)
    handler = RecordingHandler(fail_with=PermanentError("booking deleted"))
    assert asyncio.run(_dispatcher(engine, _registry(handler), clock).run_once()).dead == 1
    row = _row(engine, event_id)
    assert (row.status, row.attempts, row.last_error) == (OutboxStatus.DEAD, 1, "PermanentError")


def test_handler_timeout_is_retried(engine, clock):
    class Slow(RecordingHandler):
        timeout_seconds = 0.01

        async def handle(self, event, ctx):
            await asyncio.sleep(1)

    event_id = _publish(engine, clock)
    assert asyncio.run(_dispatcher(engine, _registry(Slow()), clock).run_once()).retried == 1
    assert _row(engine, event_id).last_error == "TimeoutError"


def test_event_without_handler_is_retried_for_a_newer_worker(engine, clock):
    event_id = _publish(engine, clock)
    assert asyncio.run(_dispatcher(engine, OutboxRegistry(), clock).run_once()).retried == 1
    assert _row(engine, event_id).last_error == "NoHandler"


def test_unreadable_payload_goes_dead(engine, clock):
    event_id = _publish(engine, clock)
    with Session(engine) as session:
        row = session.get(OutboxEventRecord, event_id)
        row.payload = {"booking_id": "not-a-uuid"}
        session.add(row)
        session.commit()
    handler = RecordingHandler()
    assert asyncio.run(_dispatcher(engine, _registry(handler), clock).run_once()).dead == 1
    assert handler.calls == []
    assert _row(engine, event_id).last_error == "ValidationError"


def test_older_schema_version_is_upcast(engine, clock):
    class BookingConfirmedV2(OutboxEvent):
        event_type = "test.booking_confirmed_v"
        schema_version = 2
        booking_id: UUID
        channel: str

        @classmethod
        def upcast(cls, payload, from_version):
            return {**payload, "channel": "discord"}

    class V1(OutboxEvent):
        event_type = "test.booking_confirmed_v"
        booking_id: UUID

    class Handler(OutboxHandler[BookingConfirmedV2]):
        event = BookingConfirmedV2
        seen: list = []

        async def handle(self, event, ctx):
            self.seen.append(event.channel)

    _publish(engine, clock, V1(booking_id=uuid4()))
    handler = Handler()
    assert asyncio.run(_dispatcher(engine, _registry(handler), clock).run_once()).succeeded == 1
    assert handler.seen == ["discord"]


def test_newer_schema_version_waits_for_a_newer_worker(engine, clock):
    class V2(OutboxEvent):
        event_type = "test.booking_confirmed"
        schema_version = 2
        booking_id: UUID

    event_id = _publish(engine, clock, V2(booking_id=uuid4()))
    handler = RecordingHandler()
    assert asyncio.run(_dispatcher(engine, _registry(handler), clock).run_once()).retried == 1
    assert handler.calls == []
    assert _row(engine, event_id).last_error == "SchemaVersionTooNew"


# ── leases ───────────────────────────────────────────────────────────────


def test_claimed_event_is_invisible_until_its_lease_expires(engine, clock):
    event_id = _publish(engine, clock)
    dispatcher = _dispatcher(engine, _registry(RecordingHandler()), clock, lease_seconds=60)

    first = dispatcher.claim_next()  # the worker then "crashes"
    assert first is not None
    assert first.attempt == 1
    assert dispatcher.claim_next() is None

    clock.advance(seconds=61)
    second = dispatcher.claim_next()
    assert second is not None
    assert (second.id, second.attempt) == (event_id, 2)
    assert second.claim_token != first.claim_token


def test_stale_claim_cannot_overwrite_the_new_owner(engine, clock):
    event_id = _publish(engine, clock)
    dispatcher = _dispatcher(engine, _registry(RecordingHandler()), clock, lease_seconds=60)
    stale = dispatcher.claim_next()
    clock.advance(seconds=61)
    current = dispatcher.claim_next()

    assert asyncio.run(dispatcher.process(stale)) == "lost"
    assert _row(engine, event_id).status == OutboxStatus.PROCESSING
    assert asyncio.run(dispatcher.process(current)) == "succeeded"
    assert _row(engine, event_id).status == OutboxStatus.SUCCEEDED


def test_expired_lease_on_the_last_attempt_goes_dead(engine, clock):
    event_id = _publish(engine, clock, max_attempts=1)
    dispatcher = _dispatcher(engine, _registry(RecordingHandler()), clock, lease_seconds=60)
    assert dispatcher.claim_next() is not None
    clock.advance(seconds=61)

    assert dispatcher.claim_next() is None
    row = _row(engine, event_id)
    assert (row.status, row.last_error) == (OutboxStatus.DEAD, "LeaseExpired")


# ── maintenance ──────────────────────────────────────────────────────────


def test_purge_deletes_only_old_succeeded_events(engine, clock):
    handler = RecordingHandler()
    dispatcher = _dispatcher(engine, _registry(handler), clock)
    old = _publish(engine, clock)
    asyncio.run(dispatcher.run_once())
    clock.advance(days=8)
    recent = _publish(engine, clock)
    asyncio.run(dispatcher.run_once())
    dead = _publish(engine, clock, max_attempts=1)
    handler.fail_with = RuntimeError()
    asyncio.run(dispatcher.run_once())
    clock.advance(days=8)

    assert dispatcher.purge_succeeded(timedelta(days=7)) == 2
    assert _row(engine, old) is None
    assert _row(engine, recent) is None
    assert _row(engine, dead).status == OutboxStatus.DEAD


def test_requeue_dead_gives_a_fresh_set_of_attempts(engine, clock):
    event_id = _publish(engine, clock)
    handler = RecordingHandler(fail_with=PermanentError())
    dispatcher = _dispatcher(engine, _registry(handler), clock)
    asyncio.run(dispatcher.run_once())

    assert dispatcher.requeue_dead(event_id) is True
    assert dispatcher.requeue_dead(event_id) is False  # already pending
    handler.fail_with = None
    assert asyncio.run(dispatcher.run_once()).succeeded == 1
    assert _row(engine, event_id).attempts == 1


# ── worker wiring ────────────────────────────────────────────────────────


def test_beat_scans_the_outbox_every_10_seconds_and_purges_daily():
    import src.infrastructure.celery.tasks.outbox_tasks  # noqa: F401  (the worker imports it via `include`)
    from src.celery_tasks import celery

    schedule = celery.conf.beat_schedule
    assert schedule["outbox-dispatch"] == {"task": "outbox.dispatch", "schedule": 10.0}
    assert schedule["outbox-purge"]["task"] == "outbox.purge"
    assert "src.infrastructure.celery.tasks.outbox_tasks" in celery.conf.include
    assert {"outbox.dispatch", "outbox.purge"} <= set(celery.tasks)


def test_lease_must_outlive_the_handler_timeout(monkeypatch):
    from src.config import Settings

    with pytest.raises(ValueError, match="OUTBOX_LEASE_SECONDS"):
        Settings(outbox_lease_seconds=30, outbox_handler_timeout_seconds=30)
