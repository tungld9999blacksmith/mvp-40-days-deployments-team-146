"""OEM integration module — sync job (JOB-VEH-001) and webhook intake (API-VEH-004).

Spec: ``docs/specs/sprint-2/api/us-017-sprint-2-spec.api.md``.

- ``OemVehicleSyncService`` pulls odometer + service history of one vehicle from
  the manufacturer and stores the new parts (ENT-414, ENT-415, ENT-416).
- ``OemWebhookService`` authenticates a manufacturer webhook and schedules a
  sync. The webhook is only a signal: data is always re-read from the API.
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from ev_contracts import WebhookEvent, WebhookEventType, verify_webhook_signature
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from src.common.core.vehicle import (
    OemSyncTrigger,
    OemUsageSource,
    ServiceRecordSource,
    UserVehicle,
    VehicleLinkStatus,
    VehicleOdometerReading,
    VehicleOemSync,
    VehicleServiceRecord,
    VehicleVerificationStatus,
)
from src.common.core.workshop.workshop import Workshop
from src.infrastructure.redis.errors import LockAcquireError

from . import errors
from .ports import (
    OemUnavailableError,
    OemVehicleDataGateway,
    OemVehicleNotFoundError,
    ServiceHistoryEntry,
    SyncLock,
    SyncScheduler,
    UsageSnapshot,
    WebhookEventStore,
)

logger = logging.getLogger(__name__)

DEFAULT_FAILURE_ALERT_THRESHOLD = 3  # BR-ENT-437, overridden by OEM_SYNC_ALERT_FAILURES
WEBHOOK_DEBOUNCE_SECONDS = 10


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC (SQLite drops tzinfo; the mock sends naive times)."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def eligible_vehicle_filter():
    """Only verified, active links are synced and shown (FF BR-010)."""
    return (
        UserVehicle.verification_status == VehicleVerificationStatus.VERIFIED,
        UserVehicle.link_status == VehicleLinkStatus.ACTIVE,
        UserVehicle.external_vehicle_id.is_not(None),
    )


def list_eligible_vehicle_ids(session: Session) -> list[UUID]:
    """Vehicles the poll job syncs (JOB-VEH-001 trigger ``poll``)."""
    stmt = select(UserVehicle.id).where(*eligible_vehicle_filter()).order_by(UserVehicle.id)
    return list(session.exec(stmt).all())


STATIC_ODOMETER_MIN_KM = 5_000
STATIC_ODOMETER_MAX_KM = 50_000


def seed_static_odometer(
    session: Session,
    user_vehicle_id: UUID,
    *,
    trigger: OemSyncTrigger = OemSyncTrigger.INITIAL,
    rng: random.Random | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> bool:
    """Give a linked vehicle a one-off random ODO instead of pulling it from the OEM.

    The ODO never increases afterwards. The sync state is marked done so the due
    status is computed right away (BR-ENT-436) without waiting for an OEM sync.
    Returns ``True`` when a reading was inserted; a vehicle with an ODO keeps it.
    The vehicle row is locked so concurrent callers cannot seed two readings.
    """
    vehicle = session.get(UserVehicle, user_vehicle_id, with_for_update=True)
    if vehicle is None or vehicle.verification_status != VehicleVerificationStatus.VERIFIED:
        return False
    now = clock()
    has_reading = session.exec(
        select(VehicleOdometerReading.id).where(VehicleOdometerReading.user_vehicle_id == user_vehicle_id)
    ).first()
    if has_reading is None:
        session.add(
            VehicleOdometerReading(
                user_vehicle_id=user_vehicle_id,
                odo_km=(rng or random).randint(STATIC_ODOMETER_MIN_KM, STATIC_ODOMETER_MAX_KM),
                recorded_at=now,
                oem_data_source=OemUsageSource.MANUAL,
                received_via=OemSyncTrigger.INITIAL,
            )
        )
    state = session.get(VehicleOemSync, user_vehicle_id) or VehicleOemSync(user_vehicle_id=user_vehicle_id)
    state.usage_synced_at = state.usage_synced_at or now
    state.service_history_synced_at = state.service_history_synced_at or now
    state.last_attempt_at = now
    state.last_trigger = trigger
    state.consecutive_failures = 0
    state.last_error_code = None
    session.add(state)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent call seeded the same vehicle first.
        session.rollback()
        return False
    return has_reading is None


@dataclass(frozen=True)
class SyncOutcome:
    status: str  # "synced" | "partial" | "failed" | "skipped"
    odometer_inserted: bool = False
    service_records_upserted: int = 0
    error_code: str | None = None


class OemVehicleSyncService:
    def __init__(
        self,
        session: Session,
        gateway: OemVehicleDataGateway,
        lock: SyncLock,
        *,
        failure_alert_threshold: int = DEFAULT_FAILURE_ALERT_THRESHOLD,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db = session
        self._gateway = gateway
        self._lock = lock
        self._failure_alert_threshold = failure_alert_threshold
        self._clock = clock

    async def sync(self, user_vehicle_id: UUID, trigger: OemSyncTrigger) -> SyncOutcome:
        vehicle = self._db.get(UserVehicle, user_vehicle_id)
        if (
            vehicle is None
            or vehicle.verification_status != VehicleVerificationStatus.VERIFIED
            or vehicle.link_status != VehicleLinkStatus.ACTIVE
            or not vehicle.external_vehicle_id
        ):
            return SyncOutcome(status="skipped", error_code="VEHICLE_NOT_ELIGIBLE")

        if not await self._lock.acquire(user_vehicle_id):
            return SyncOutcome(status="skipped", error_code="SYNC_IN_PROGRESS")
        try:
            return await self._sync_locked(vehicle, trigger)
        finally:
            await self._lock.release(user_vehicle_id)

    async def _sync_locked(self, vehicle: UserVehicle, trigger: OemSyncTrigger) -> SyncOutcome:
        state = self._db.get(VehicleOemSync, vehicle.id) or VehicleOemSync(user_vehicle_id=vehicle.id)
        state.last_attempt_at = self._clock()
        state.last_trigger = trigger
        self._db.add(state)
        self._db.commit()

        external_id = vehicle.external_vehicle_id
        error_codes: list[str] = []
        inserted = False
        upserted = 0

        # O6 and O7 are independent: a failure of one does not block the other.
        try:
            usage = await self._gateway.get_usage(external_id)
            inserted = self._store_usage(vehicle.id, usage, trigger)
            state.usage_synced_at = self._clock()
        except OemVehicleNotFoundError:
            error_codes.append("OEM_VEHICLE_NOT_FOUND")
        except OemUnavailableError as exc:
            logger.warning("OEM usage sync failed for %s: %s", vehicle.id, exc)
            error_codes.append("OEM_UNAVAILABLE")

        try:
            history = await self._gateway.get_service_history(external_id)
            upserted = self._store_service_history(vehicle.id, history)
            state.service_history_synced_at = self._clock()
        except OemVehicleNotFoundError:
            error_codes.append("OEM_VEHICLE_NOT_FOUND")
        except OemUnavailableError as exc:
            logger.warning("OEM service-history sync failed for %s: %s", vehicle.id, exc)
            error_codes.append("OEM_UNAVAILABLE")

        if error_codes:
            state.consecutive_failures += 1
            state.last_error_code = error_codes[0]
            if state.consecutive_failures >= self._failure_alert_threshold:
                logger.error(
                    "OEM sync for vehicle %s failed %s times in a row (%s)",
                    vehicle.id,
                    state.consecutive_failures,
                    state.last_error_code,
                )
        else:
            state.consecutive_failures = 0
            state.last_error_code = None
        self._db.add(state)
        self._db.commit()

        if not error_codes:
            status = "synced"
        elif len(error_codes) == 2:
            status = "failed"
        else:
            status = "partial"
        return SyncOutcome(
            status=status,
            odometer_inserted=inserted,
            service_records_upserted=upserted,
            error_code=error_codes[0] if error_codes else None,
        )

    # ------------------------------------------------------------ odometer
    def _store_usage(self, user_vehicle_id: UUID, usage: UsageSnapshot | None, trigger: OemSyncTrigger) -> bool:
        """Insert a new snapshot if it is newer than the last one (BR-ENT-431)."""
        if usage is None:
            return False
        recorded_at = as_utc(usage.last_updated_at)
        latest = self._db.exec(
            select(func.max(VehicleOdometerReading.recorded_at)).where(
                VehicleOdometerReading.user_vehicle_id == user_vehicle_id
            )
        ).one()
        if latest is not None and recorded_at <= as_utc(latest):
            return False

        current = self._db.exec(
            select(func.max(VehicleOdometerReading.odo_km)).where(
                VehicleOdometerReading.user_vehicle_id == user_vehicle_id
            )
        ).one()
        if current is not None and usage.current_km < current:
            # BR-ENT-432: keep the value for traceability, it never lowers the effective ODO.
            logger.warning(
                "odometer_decrease vehicle=%s previous=%s received=%s",
                user_vehicle_id,
                current,
                usage.current_km,
            )

        try:
            source = OemUsageSource(usage.data_source)
        except ValueError:
            source = OemUsageSource.TELEMATICS
        self._db.add(
            VehicleOdometerReading(
                user_vehicle_id=user_vehicle_id,
                odo_km=usage.current_km,
                recorded_at=recorded_at,
                oem_data_source=source,
                received_via=trigger,
            )
        )
        try:
            self._db.commit()
        except IntegrityError:
            # A concurrent sync stored the same snapshot first.
            self._db.rollback()
            return False
        return True

    # ------------------------------------------------------ service history
    def _store_service_history(self, user_vehicle_id: UUID, history: list[ServiceHistoryEntry]) -> int:
        """Upsert manufacturer records by order id (BR-ENT-433). Returns rows changed.

        Records are never deleted, even if the manufacturer drops them (Q-311).
        """
        existing = {
            record.external_order_id: record
            for record in self._db.exec(
                select(VehicleServiceRecord).where(
                    VehicleServiceRecord.user_vehicle_id == user_vehicle_id,
                    VehicleServiceRecord.source == ServiceRecordSource.OEM,
                )
            ).all()
        }
        center_ids = {e.service_center_id for e in history if e.service_center_id}
        workshops = (
            {
                w.external_center_id: w.id
                for w in self._db.exec(select(Workshop).where(Workshop.external_center_id.in_(center_ids))).all()
            }
            if center_ids
            else {}
        )

        now = self._clock()
        changed = 0
        for entry in history:
            fields = {
                "service_date": entry.service_date,
                "odo_km": entry.km_at_service,
                "external_center_id": entry.service_center_id,
                "workshop_id": workshops.get(entry.service_center_id),
                "items_done": entry.items_done,
                "is_periodic": entry.is_periodic,
            }
            record = existing.get(entry.order_id)
            if record is None:
                record = VehicleServiceRecord(
                    user_vehicle_id=user_vehicle_id,
                    source=ServiceRecordSource.OEM,
                    external_order_id=entry.order_id,
                    synced_at=now,
                    **fields,
                )
            elif all(getattr(record, key) == value for key, value in fields.items()):
                continue
            else:
                for key, value in fields.items():
                    setattr(record, key, value)
                record.synced_at = now
            self._db.add(record)
            changed += 1
        self._db.commit()
        return changed


@dataclass(frozen=True)
class WebhookResult:
    event_id: str
    accepted: bool = True
    duplicate: bool = False
    ignored: bool = False


class OemWebhookService:
    """Authenticates manufacturer webhooks and schedules syncs (API-VEH-004)."""

    def __init__(
        self,
        session: Session,
        scheduler: SyncScheduler,
        event_store: WebhookEventStore,
        *,
        secret: str,
        tolerance_seconds: int = 300,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db = session
        self._scheduler = scheduler
        self._events = event_store
        self._secret = secret
        self._tolerance = tolerance_seconds
        self._clock = clock

    async def handle(
        self,
        *,
        event_id: str | None,
        timestamp: str | None,
        signature: str | None,
        raw_body: bytes,
    ) -> WebhookResult:
        self._check_timestamp(timestamp)
        if not self._secret:
            logger.error("OEM_WEBHOOK_SECRET is not configured; rejecting webhook")
            raise errors.WebhookSignatureInvalidError()
        if not signature or not verify_webhook_signature(self._secret, timestamp, raw_body, signature):
            raise errors.WebhookSignatureInvalidError()
        if not event_id or len(event_id) > 128:
            raise errors.InvalidWebhookRequestError("X-OEM-Event-Id header is required.")

        event = self._parse(raw_body)

        try:
            async with self._events.processing(f"event:{event_id}"):
                if await self._events.event_processed(event_id):
                    return WebhookResult(event_id=event_id, duplicate=True)
                vehicle_id = await run_in_threadpool(self._find_vehicle_id, event.vehicle_id)
                if vehicle_id is None:
                    await self._events.mark_event_processed(event_id)
                    return WebhookResult(event_id=event_id, ignored=True)
                # A different event must not be acknowledged while scheduling
                # this vehicle is still pending (and might fail).
                async with self._events.processing(f"vehicle:{vehicle_id}"):
                    if not await self._events.is_debounced(vehicle_id):
                        await run_in_threadpool(
                            self._scheduler.schedule,
                            vehicle_id,
                            OemSyncTrigger.WEBHOOK,
                            delay_seconds=WEBHOOK_DEBOUNCE_SECONDS,
                        )
                        await self._events.mark_debounced(vehicle_id)
                    await self._events.mark_event_processed(event_id)
        except LockAcquireError as exc:
            raise errors.WebhookProcessingError() from exc
        logger.info(
            "OEM webhook %s %s accepted for vehicle %s",
            event_id,
            event.event_type.value,
            vehicle_id,
        )
        return WebhookResult(event_id=event_id)

    def _find_vehicle_id(self, external_vehicle_id: str) -> UUID | None:
        try:
            return self._db.exec(
                select(UserVehicle.id).where(
                    UserVehicle.external_vehicle_id == external_vehicle_id, *eligible_vehicle_filter()
                )
            ).first()
        finally:
            # Read-only: end the transaction so the pooled connection is returned before
            # the Redis/Celery awaits. Otherwise each webhook of an OEM burst holds a
            # Supavisor connection "idle in transaction" and starves every other API.
            self._db.rollback()

    def _check_timestamp(self, timestamp: str | None) -> None:
        try:
            sent_at = int(timestamp or "")
        except ValueError as exc:
            raise errors.WebhookTimestampExpiredError() from exc
        if abs(self._clock().timestamp() - sent_at) > self._tolerance:
            raise errors.WebhookTimestampExpiredError()

    @staticmethod
    def _parse(raw_body: bytes) -> WebhookEvent:
        try:
            payload = json.loads(raw_body)
        except ValueError as exc:
            raise errors.InvalidWebhookRequestError("Body is not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise errors.InvalidWebhookRequestError()
        event_type = payload.get("eventType")
        if isinstance(event_type, str) and event_type not in {e.value for e in WebhookEventType}:
            raise errors.UnsupportedEventTypeError(event_type)
        try:
            return WebhookEvent.model_validate(payload)
        except ValidationError as exc:
            raise errors.InvalidWebhookRequestError() from exc
