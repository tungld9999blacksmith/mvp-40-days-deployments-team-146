"""Tests for the OEM sync job (JOB-VEH-001) and webhook intake (API-VEH-004)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from ev_contracts import sign_webhook
from fakeredis import FakeAsyncRedis
from sqlmodel import select

from src.common.core.vehicle import (
    OemSyncTrigger,
    ServiceRecordSource,
    VehicleLinkStatus,
    VehicleOdometerReading,
    VehicleOemSync,
    VehicleServiceRecord,
    VehicleVerificationStatus,
)
from src.common.core.workshop.workshop import Workshop, WorkshopStatus
from src.modules.oem_integration import errors
from src.modules.oem_integration.adapters import RedisWebhookEventStore
from src.modules.oem_integration.service import (
    STATIC_ODOMETER_MAX_KM,
    STATIC_ODOMETER_MIN_KM,
    WEBHOOK_DEBOUNCE_SECONDS,
    OemVehicleSyncService,
    OemWebhookService,
    list_eligible_vehicle_ids,
    seed_static_odometer,
)
from tests._user_vehicle import (
    NOW,
    MemoryEventStore,
    MemoryLock,
    OemUnavailableError,
    OemVehicleNotFoundError,
    RecordingScheduler,
    ServiceHistoryEntry,
    StubDataGateway,
    UsageSnapshot,
    add_odometer,
    add_owner,
    add_vehicle,
    make_session,
)

SECRET = "test-secret"


@pytest_asyncio.fixture(params=["memory", "redis"])
async def event_store(request):
    if request.param == "memory":
        yield MemoryEventStore()
    else:
        redis = FakeAsyncRedis()
        yield RedisWebhookEventStore(redis, key_prefix="webhook-test")
        await redis.aclose()


@pytest.fixture
def session():
    yield from make_session()


@pytest.fixture
def vehicle(session):
    return add_vehicle(session, add_owner(session))


def _usage(km: int, at: datetime = NOW, source: str = "telematics") -> UsageSnapshot:
    return UsageSnapshot(current_km=km, data_source=source, last_updated_at=at)


def _entry(
    order_id: str = "SH-001",
    km: int = 11_900,
    center: str | None = "SC-01",
    is_periodic: bool = True,
):
    return ServiceHistoryEntry(
        order_id=order_id,
        service_center_id=center,
        service_date=date(2026, 9, 1),
        km_at_service=km,
        items_done="Brake check",
        is_periodic=is_periodic,
    )


def _sync_service(session, gateway, lock=None, **kwargs):
    return OemVehicleSyncService(session, gateway, lock or MemoryLock(), clock=lambda: NOW, **kwargs)


def _readings(session, vehicle):
    return session.exec(
        select(VehicleOdometerReading).where(VehicleOdometerReading.user_vehicle_id == vehicle.id)
    ).all()


# ── JOB-VEH-001 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_stores_odometer_history_and_state(session, vehicle):
    gateway = StubDataGateway(usage=_usage(11_600), history=[_entry()])

    outcome = await _sync_service(session, gateway).sync(vehicle.id, OemSyncTrigger.POLL)

    assert outcome.status == "synced"
    assert outcome.odometer_inserted and outcome.service_records_upserted == 1
    (reading,) = _readings(session, vehicle)
    assert reading.odo_km == 11_600 and reading.received_via is OemSyncTrigger.POLL
    record = session.exec(select(VehicleServiceRecord)).one()
    assert record.source is ServiceRecordSource.OEM and record.external_order_id == "SH-001"
    state = session.get(VehicleOemSync, vehicle.id)
    assert state.usage_synced_at is not None and state.service_history_synced_at is not None
    assert state.consecutive_failures == 0 and state.last_trigger is OemSyncTrigger.POLL


@pytest.mark.asyncio
async def test_same_snapshot_is_not_stored_twice(session, vehicle):
    service = _sync_service(session, StubDataGateway(usage=_usage(11_600)))

    await service.sync(vehicle.id, OemSyncTrigger.POLL)
    second = await service.sync(vehicle.id, OemSyncTrigger.WEBHOOK)

    assert second.odometer_inserted is False
    assert len(_readings(session, vehicle)) == 1


@pytest.mark.asyncio
async def test_lower_value_is_kept_for_traceability_br_ent_432(session, vehicle, caplog):
    gateway = StubDataGateway(usage=_usage(12_300))
    service = _sync_service(session, gateway)
    await service.sync(vehicle.id, OemSyncTrigger.POLL)

    gateway.usage = _usage(12_100, NOW + timedelta(hours=1))
    await service.sync(vehicle.id, OemSyncTrigger.POLL)

    assert sorted(r.odo_km for r in _readings(session, vehicle)) == [12_100, 12_300]
    assert "odometer_decrease" in caplog.text


@pytest.mark.asyncio
async def test_no_usage_data_is_success_without_row(session, vehicle):
    outcome = await _sync_service(session, StubDataGateway(usage=None)).sync(vehicle.id, OemSyncTrigger.INITIAL)

    assert outcome.status == "synced"
    assert _readings(session, vehicle) == []
    assert session.get(VehicleOemSync, vehicle.id).usage_synced_at is not None


@pytest.mark.asyncio
async def test_history_upsert_updates_changed_rows_only(session, vehicle):
    gateway = StubDataGateway(history=[_entry()])
    service = _sync_service(session, gateway)
    await service.sync(vehicle.id, OemSyncTrigger.POLL)

    unchanged = await service.sync(vehicle.id, OemSyncTrigger.POLL)
    gateway.history = [_entry(km=12_050), _entry("SH-002", km=24_000)]
    changed = await service.sync(vehicle.id, OemSyncTrigger.POLL)

    assert unchanged.service_records_upserted == 0
    assert changed.service_records_upserted == 2
    records = {r.external_order_id: r.odo_km for r in session.exec(select(VehicleServiceRecord))}
    assert records == {"SH-001": 12_050, "SH-002": 24_000}


@pytest.mark.asyncio
async def test_history_stores_and_updates_periodic_flag_q304(session, vehicle):
    gateway = StubDataGateway(history=[_entry("SH-001"), _entry("SH-002", is_periodic=False)])
    service = _sync_service(session, gateway)

    await service.sync(vehicle.id, OemSyncTrigger.POLL)
    flags = {r.external_order_id: r.is_periodic for r in session.exec(select(VehicleServiceRecord))}
    assert flags == {"SH-001": True, "SH-002": False}

    gateway.history = [_entry("SH-001"), _entry("SH-002", is_periodic=True)]
    changed = await service.sync(vehicle.id, OemSyncTrigger.POLL)
    assert changed.service_records_upserted == 1
    assert all(r.is_periodic for r in session.exec(select(VehicleServiceRecord)))


@pytest.mark.asyncio
async def test_history_dropped_by_oem_is_kept_q311(session, vehicle):
    gateway = StubDataGateway(history=[_entry("SH-001"), _entry("SH-002", km=24_000)])
    service = _sync_service(session, gateway)
    await service.sync(vehicle.id, OemSyncTrigger.POLL)

    gateway.history = [_entry("SH-001")]
    await service.sync(vehicle.id, OemSyncTrigger.POLL)

    orders = {r.external_order_id for r in session.exec(select(VehicleServiceRecord))}
    assert orders == {"SH-001", "SH-002"}


@pytest.mark.asyncio
async def test_history_maps_service_center_to_workshop(session, vehicle):
    workshop = Workshop(
        external_center_id="SC-01",
        name="VinFast Smart City",
        region="north",
        type="dealer",
        address="Ha Noi",
        total_technicians=4,
        status=WorkshopStatus.INACTIVE,
    )
    session.add(workshop)
    session.commit()

    await _sync_service(session, StubDataGateway(history=[_entry()])).sync(vehicle.id, OemSyncTrigger.POLL)

    assert session.exec(select(VehicleServiceRecord)).one().workshop_id == workshop.id


@pytest.mark.asyncio
async def test_partial_failure_counts_and_keeps_other_side(session, vehicle):
    gateway = StubDataGateway(usage=_usage(11_600), history_error=OemUnavailableError("timeout"))

    outcome = await _sync_service(session, gateway).sync(vehicle.id, OemSyncTrigger.POLL)

    assert outcome.status == "partial" and outcome.error_code == "OEM_UNAVAILABLE"
    state = session.get(VehicleOemSync, vehicle.id)
    assert state.usage_synced_at is not None
    assert state.service_history_synced_at is None
    assert state.consecutive_failures == 1
    assert len(_readings(session, vehicle)) == 1


@pytest.mark.asyncio
async def test_repeated_failures_alert_and_reset_on_success(session, vehicle, caplog):
    gateway = StubDataGateway(
        usage_error=OemVehicleNotFoundError("VEH-006"),
        history_error=OemVehicleNotFoundError("VEH-006"),
    )
    service = _sync_service(session, gateway)
    for _ in range(3):
        outcome = await service.sync(vehicle.id, OemSyncTrigger.POLL)

    assert outcome.status == "failed" and outcome.error_code == "OEM_VEHICLE_NOT_FOUND"
    assert session.get(VehicleOemSync, vehicle.id).consecutive_failures == 3
    assert "failed 3 times in a row" in caplog.text

    gateway.usage_error = gateway.history_error = None
    await service.sync(vehicle.id, OemSyncTrigger.POLL)
    state = session.get(VehicleOemSync, vehicle.id)
    assert state.consecutive_failures == 0 and state.last_error_code is None


@pytest.mark.asyncio
async def test_failure_alert_threshold_is_configurable_q312(session, vehicle, caplog):
    gateway = StubDataGateway(usage_error=OemUnavailableError("down"), history_error=OemUnavailableError("down"))
    service = _sync_service(session, gateway, failure_alert_threshold=2)

    await service.sync(vehicle.id, OemSyncTrigger.POLL)
    assert "in a row" not in caplog.text
    await service.sync(vehicle.id, OemSyncTrigger.POLL)

    assert "failed 2 times in a row" in caplog.text


@pytest.mark.asyncio
async def test_ineligible_vehicle_is_skipped(session):
    user = add_owner(session)
    unlinked = add_vehicle(session, user, link_status=VehicleLinkStatus.UNLINKED)

    outcome = await _sync_service(session, StubDataGateway(usage=_usage(1))).sync(unlinked.id, OemSyncTrigger.POLL)

    assert outcome.status == "skipped"
    assert list_eligible_vehicle_ids(session) == []


@pytest.mark.asyncio
async def test_concurrent_sync_is_skipped_by_lock(session, vehicle):
    lock = MemoryLock()
    lock.held.add(vehicle.id)

    outcome = await _sync_service(session, StubDataGateway(), lock).sync(vehicle.id, OemSyncTrigger.WEBHOOK)

    assert outcome.status == "skipped" and outcome.error_code == "SYNC_IN_PROGRESS"


# ── Static ODO (replaces the OEM pull) ─────────────────────────────────────


def test_static_odometer_is_random_in_range_and_marks_sync_done(session, vehicle):
    assert seed_static_odometer(session, vehicle.id, clock=lambda: NOW) is True

    (reading,) = _readings(session, vehicle)
    assert STATIC_ODOMETER_MIN_KM <= reading.odo_km <= STATIC_ODOMETER_MAX_KM
    state = session.get(VehicleOemSync, vehicle.id)
    assert state.usage_synced_at is not None and state.service_history_synced_at is not None


def test_static_odometer_never_increases(session, vehicle):
    seed_static_odometer(session, vehicle.id, clock=lambda: NOW)
    first = _readings(session, vehicle)[0].odo_km

    later = NOW + timedelta(days=3)
    assert seed_static_odometer(session, vehicle.id, clock=lambda: later) is False

    assert [r.odo_km for r in _readings(session, vehicle)] == [first]


def test_static_odometer_keeps_an_existing_reading(session, vehicle):
    add_odometer(session, vehicle, 75_232)

    seed_static_odometer(session, vehicle.id, clock=lambda: NOW)

    assert [r.odo_km for r in _readings(session, vehicle)] == [75_232]


def test_static_odometer_uses_the_full_range(session, vehicle):
    class Edge:
        def randint(self, low, high):
            return high

    seed_static_odometer(session, vehicle.id, rng=Edge(), clock=lambda: NOW)

    assert _readings(session, vehicle)[0].odo_km == STATIC_ODOMETER_MAX_KM


# ── API-VEH-004 service ────────────────────────────────────────────────────


def _webhook(session, scheduler=None, store=None, secret=SECRET):
    return OemWebhookService(
        session,
        scheduler or RecordingScheduler(),
        store or MemoryEventStore(),
        secret=secret,
        clock=lambda: NOW,
    )


def _signed(body: dict | bytes, *, ts: int | None = None, secret: str = SECRET):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    ts = ts if ts is not None else int(NOW.timestamp())
    return {
        "event_id": "evt_1",
        "timestamp": str(ts),
        "signature": sign_webhook(secret, ts, raw),
        "raw_body": raw,
    }


def _event(vehicle_id: str = "VEH-006", event_type: str = "vehicle.usage.updated"):
    return {"eventType": event_type, "vehicleId": vehicle_id, "occurredAt": "2026-09-28T02:00:00Z"}


@pytest.mark.asyncio
async def test_webhook_schedules_debounced_sync(session, vehicle):
    scheduler = RecordingScheduler()
    service = _webhook(session, scheduler)

    result = await service.handle(**_signed(_event()))
    second = await service.handle(**{**_signed(_event()), "event_id": "evt_2"})

    assert result.accepted and not result.duplicate and not result.ignored
    assert second.accepted
    assert scheduler.calls == [(vehicle.id, OemSyncTrigger.WEBHOOK, WEBHOOK_DEBOUNCE_SECONDS)]


@pytest.mark.asyncio
async def test_webhook_releases_db_connection_before_scheduling(session, vehicle):
    """A webhook burst must not pin pooler connections while Redis/Celery work runs."""
    open_during_schedule: list[bool] = []

    class Probe(RecordingScheduler):
        def schedule(self, user_vehicle_id, trigger, *, delay_seconds=0):
            open_during_schedule.append(session.in_transaction())
            super().schedule(user_vehicle_id, trigger, delay_seconds=delay_seconds)

    await _webhook(session, Probe()).handle(**_signed(_event()))

    assert open_during_schedule == [False]


@pytest.mark.asyncio
async def test_webhook_duplicate_event_is_not_reprocessed(session, vehicle):
    scheduler = RecordingScheduler()
    service = _webhook(session, scheduler, MemoryEventStore())
    await service.handle(**_signed(_event()))

    result = await service.handle(**_signed(_event()))

    assert result.duplicate is True
    assert len(scheduler.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["database", "broker"])
async def test_webhook_retry_after_transient_failure_is_not_dropped(session, vehicle, stage, monkeypatch, event_store):
    scheduler, store = RecordingScheduler(), event_store
    service = _webhook(session, scheduler, store)
    target = service if stage == "database" else scheduler
    method = "_find_vehicle_id" if stage == "database" else "schedule"
    original = getattr(target, method)

    def fail(*args, **kwargs):
        raise RuntimeError("temporarily unavailable")

    monkeypatch.setattr(target, method, fail)
    with pytest.raises(RuntimeError):
        await service.handle(**_signed(_event()))
    assert not await store.event_processed("evt_1")
    assert not await store.is_debounced(vehicle.id)

    monkeypatch.setattr(target, method, original)
    result = await service.handle(**_signed(_event()))
    assert not result.duplicate
    assert len(scheduler.calls) == 1


@pytest.mark.asyncio
async def test_concurrent_webhooks_schedule_vehicle_once(session, vehicle, event_store):
    import asyncio

    scheduler = RecordingScheduler()
    service = _webhook(session, scheduler, event_store)
    results = await asyncio.gather(
        service.handle(**_signed(_event())),
        service.handle(**{**_signed(_event()), "event_id": "evt_2"}),
        service.handle(**_signed(_event())),
    )
    assert sum(result.duplicate for result in results) == 1
    assert len(scheduler.calls) == 1


@pytest.mark.asyncio
async def test_webhook_for_unknown_vehicle_is_ignored(session, vehicle):
    scheduler = RecordingScheduler()

    result = await _webhook(session, scheduler).handle(**_signed(_event("VEH-999")))

    assert result.ignored is True and scheduler.calls == []


@pytest.mark.asyncio
async def test_webhook_bad_signature_rejected(session, vehicle):
    request = _signed(_event(), secret="wrong-secret")

    with pytest.raises(errors.WebhookSignatureInvalidError):
        await _webhook(session).handle(**request)


@pytest.mark.asyncio
async def test_webhook_tampered_body_rejected(session, vehicle):
    request = _signed(_event())
    request["raw_body"] = json.dumps(_event("VEH-007")).encode()

    with pytest.raises(errors.WebhookSignatureInvalidError):
        await _webhook(session).handle(**request)


@pytest.mark.asyncio
async def test_webhook_expired_timestamp_rejected(session, vehicle):
    request = _signed(_event(), ts=int(NOW.timestamp()) - 301)

    with pytest.raises(errors.WebhookTimestampExpiredError):
        await _webhook(session).handle(**request)


@pytest.mark.asyncio
async def test_webhook_rejected_when_secret_not_configured(session, vehicle):
    with pytest.raises(errors.WebhookSignatureInvalidError):
        await _webhook(session, secret="").handle(**_signed(_event(), secret=""))


@pytest.mark.asyncio
async def test_webhook_unsupported_event_type(session, vehicle):
    with pytest.raises(errors.UnsupportedEventTypeError):
        await _webhook(session).handle(**_signed(_event(event_type="vehicle.deleted")))


@pytest.mark.asyncio
async def test_webhook_invalid_payload(session, vehicle):
    with pytest.raises(errors.InvalidWebhookRequestError):
        await _webhook(session).handle(**_signed(b"not-json"))

    with pytest.raises(errors.InvalidWebhookRequestError):
        await _webhook(session).handle(**_signed({"eventType": "vehicle.usage.updated"}))


@pytest.mark.asyncio
async def test_webhook_signed_by_mock_is_accepted(session, vehicle):
    """Contract check: mock-ev-system signs exactly what the backend verifies."""
    from ev_contracts import WebhookEventType
    from mock_ev_system.webhooks import build_request

    event_id, headers, body = build_request(WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-006", SECRET, now=NOW)
    scheduler = RecordingScheduler()

    result = await _webhook(session, scheduler).handle(
        event_id=headers["X-OEM-Event-Id"],
        timestamp=headers["X-OEM-Timestamp"],
        signature=headers["X-OEM-Signature"],
        raw_body=body,
    )

    assert result.event_id == event_id and result.accepted and not result.ignored
    assert scheduler.calls == [(vehicle.id, OemSyncTrigger.WEBHOOK, WEBHOOK_DEBOUNCE_SECONDS)]


def test_list_eligible_vehicle_ids(session, vehicle):
    assert list_eligible_vehicle_ids(session) == [vehicle.id]


def test_now_is_timezone_aware():
    assert NOW.tzinfo is UTC
    assert datetime.now(UTC).tzinfo is UTC


def test_static_odometer_records_the_trigger(session, vehicle):
    seed_static_odometer(session, vehicle.id, trigger=OemSyncTrigger.WEBHOOK, clock=lambda: NOW)

    assert session.get(VehicleOemSync, vehicle.id).last_trigger == OemSyncTrigger.WEBHOOK


def test_static_odometer_skips_unverified_vehicle(session, vehicle):
    vehicle.verification_status = VehicleVerificationStatus.PENDING
    session.add(vehicle)
    session.commit()

    assert seed_static_odometer(session, vehicle.id, clock=lambda: NOW) is False
    assert _readings(session, vehicle) == []


@pytest.mark.parametrize(
    ("app_env", "mode", "static"),
    [
        ("production", "", False),
        ("development", "", True),
        ("development", "oem", False),
    ],
)
def test_static_odometer_is_never_the_production_default(app_env, mode, static):
    from src.config import Settings
    from src.modules.oem_integration.adapters import CelerySyncScheduler, StaticOdometerScheduler
    from src.modules.oem_integration.dependency import sync_scheduler_for

    settings = Settings(app_env=app_env, oem_sync_mode=mode)
    assert settings.uses_static_odometer() is static
    expected = StaticOdometerScheduler if static else CelerySyncScheduler
    assert isinstance(sync_scheduler_for(settings), expected)


@pytest.mark.asyncio
async def test_webhook_lock_contention_returns_processing_error(session, vehicle, monkeypatch):
    from contextlib import asynccontextmanager

    from src.infrastructure.redis.errors import LockAcquireError

    scheduler, store = RecordingScheduler(), MemoryEventStore()

    @asynccontextmanager
    async def busy(key):
        raise LockAcquireError(key)
        yield

    monkeypatch.setattr(store, "processing", busy)
    with pytest.raises(errors.WebhookProcessingError):
        await _webhook(session, scheduler, store).handle(**_signed(_event()))
    assert not await store.event_processed("evt_1")
    assert scheduler.calls == []
    assert errors.ERROR_STATUS["WEBHOOK_PROCESSING"] == 503


def test_static_scheduler_seeds_through_its_own_session(session, vehicle, monkeypatch):
    from src.infrastructure.supabase import db
    from src.modules.oem_integration.adapters import StaticOdometerScheduler

    monkeypatch.setattr(db, "engine", session.get_bind())
    StaticOdometerScheduler().schedule(vehicle.id, OemSyncTrigger.WEBHOOK)

    session.expire_all()
    assert len(_readings(session, vehicle)) == 1
    assert session.get(VehicleOemSync, vehicle.id).last_trigger == OemSyncTrigger.WEBHOOK


def test_production_rejects_static_odometer_mode():
    from pydantic import ValidationError

    from src.config import Settings

    with pytest.raises(ValidationError, match="OEM_SYNC_MODE=static"):
        Settings(app_env="production", oem_sync_mode="static")


def test_self_heal_seeds_on_one_connection_and_answers_with_the_seed(session, vehicle, monkeypatch):
    """The first status read seeds the demo ODO and already reflects it (no UNKNOWN round trip)."""
    from src.infrastructure.supabase import db
    from src.modules.oem_integration.adapters import StaticOdometerScheduler
    from src.modules.user_vehicle.domain import DueConfig
    from src.modules.user_vehicle.service import UserVehicleService

    monkeypatch.setattr(db, "engine", session.get_bind())
    in_transaction = []

    class Probe(StaticOdometerScheduler):
        def schedule(self, user_vehicle_id, trigger, *, delay_seconds=0):
            in_transaction.append(session.in_transaction())
            super().schedule(user_vehicle_id, trigger, delay_seconds=delay_seconds)

    status = UserVehicleService(session, Probe(), config=DueConfig()).get_maintenance_status(vehicle)

    assert in_transaction == [False]  # the request's read transaction ended before the seed
    assert status.unknown_reason != "OEM_DATA_NOT_SYNCED"
