"""Shared test helpers for FEAT-VEH-001 (user_vehicle + oem_integration modules).

In-memory SQLite with the tables the feature reads/writes, seed helpers and
stubs for the OEM gateway, sync lock, sync scheduler and webhook event store —
tests never touch Postgres, Redis, Celery or the mock HTTP service.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, MetaData, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

# Importing the core package registers every table (FK targets included).
import src.common.core  # noqa: F401
from src.common.core.conversation.conversation import Conversation
from src.common.core.conversation.message import ChatMessage
from src.common.core.identity.vehicle_user import OnboardingStatus, UserStatus, VehicleUser
from src.common.core.identity.user_discord_link import DiscordLinkStatus, UserDiscordLink
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.maintenance.booking import Booking
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.maintenance.reminder import Reminder
from src.common.core.notification import (
    ReminderDelivery,
    UserNotificationChannel,
    UserNotificationSetting,
)
from src.common.core.vehicle import (
    OemSyncTrigger,
    UserVehicle,
    VehicleLinkStatus,
    VehicleOdometerReading,
    VehicleOemSync,
    VehicleServiceRecord,
    VehicleVerificationStatus,
)
from src.common.core.workshop.service_price import ServicePrice
from src.common.core.workshop.workshop import Workshop
from src.modules.oem_integration.ports import (
    OemUnavailableError,
    OemVehicleDataGateway,
    OemVehicleNotFoundError,
    ServiceHistoryEntry,
    SyncLock,
    SyncScheduler,
    UsageSnapshot,
    WebhookEventStore,
)
from src.modules.vehicle_owner_onboarding.domain import (
    UserLocation,
    VehicleWarranty,
    WarrantyComponent,
    WarrantyStatus,
)

TABLES = [
    VehicleUser.__table__,
    WorkshopOwner.__table__,
    Workshop.__table__,
    UserVehicle.__table__,
    VehicleWarranty.__table__,
    MaintenanceRule.__table__,
    Booking.__table__,  # FK target of vehicle_service_record.booking_id
    Conversation.__table__,  # FK target of chat_message.conversation_id
    ChatMessage.__table__,  # FK target of booking.source_message_id
    VehicleOdometerReading.__table__,
    VehicleServiceRecord.__table__,
    VehicleOemSync.__table__,
    Reminder.__table__,
    ReminderDelivery.__table__,
    UserNotificationSetting.__table__,
    UserNotificationChannel.__table__,
    UserDiscordLink.__table__,
    ServicePrice.__table__,
    UserLocation.__table__,
]

# 2026-09-28 09:00 in Vietnam (UTC+7).
NOW = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)
PURCHASE_DATE = date(2025, 10, 15)
MODEL_ID = "MDL-03"
EXTERNAL_VEHICLE_ID = "VEH-006"
VIN = "LVVDB11B1PE000001"


def _make_sqlite_compatible(table: Table) -> None:
    """Rewrite PostgreSQL-only parts of a *copied* table so SQLite can create it.

    - ``JSONB`` columns -> ``JSON`` (chat_message.citations / tool_calls / refs / card).
    - Generated ``TSVECTOR`` column (``to_tsvector(...)``) -> plain nullable ``TEXT``
      (chat_message.search_vector; keyword search is not exercised on SQLite).
    - CHECK with a regex (``~``) is dropped (maintenance_rule).
    - CHECK using ``jsonb_array_length`` is kept, rewritten to SQLite's
      ``json_array_length`` (chat_message role-shape checks).

    GIN / ``postgresql_where`` index options are ignored by the SQLite dialect.
    """
    for column in table.columns:
        if isinstance(column.type, JSONB):
            column.type = JSON()
        elif isinstance(column.type, TSVECTOR):
            column.type = Text()
            column.computed = None
            column.server_default = None
    for constraint in list(table.constraints):
        if not isinstance(constraint, CheckConstraint):
            continue
        sql = str(constraint.sqltext)
        if "~" in sql:
            table.constraints.discard(constraint)
        elif "jsonb_array_length" in sql:
            constraint.sqltext = text(sql.replace("jsonb_array_length", "json_array_length"))


def make_session() -> Iterator[Session]:
    """Fresh in-memory SQLite session with the FEAT-VEH-001 tables.

    Tables are created from a copy of the metadata made SQLite-compatible
    (see ``_make_sqlite_compatible``); the real models are left untouched.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata = MetaData()
    for table in TABLES:
        _make_sqlite_compatible(table.to_metadata(metadata))
    metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# ── Seed helpers ────────────────────────────────────────────────────────────
def add_owner(
    session: Session,
    *,
    uid: str = "uid-1",
    email: str = "owner1@example.com",
    onboarding_status: OnboardingStatus = OnboardingStatus.ACTIVE,
    status: UserStatus = UserStatus.ACTIVE,
) -> VehicleUser:
    user = VehicleUser(
        firebase_uid=uid, email=email, onboarding_status=onboarding_status, status=status
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def add_vehicle(
    session: Session,
    user: VehicleUser,
    *,
    vin: str = VIN,
    external_vehicle_id: str | None = EXTERNAL_VEHICLE_ID,
    verification_status: VehicleVerificationStatus = VehicleVerificationStatus.VERIFIED,
    link_status: VehicleLinkStatus = VehicleLinkStatus.ACTIVE,
    with_warranty: bool = True,
) -> UserVehicle:
    vehicle = UserVehicle(
        user_id=user.user_id,
        vin=vin,
        license_plate="30A12345",
        declared_model_id=MODEL_ID,
        external_vehicle_id=external_vehicle_id,
        external_owner_id="OWN-004",
        external_model_id=MODEL_ID,
        model_name="VF6",
        trim="Plus",
        color="White",
        manufacture_date=date(2025, 8, 20),
        production_year=2025,
        verification_status=verification_status,
        link_status=link_status,
    )
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)
    if with_warranty:
        session.add(
            VehicleWarranty(
                user_vehicle_id=vehicle.id,
                external_warranty_id=f"WAR-{vehicle.id.hex[:6]}",
                component=WarrantyComponent.BATTERY,
                start_date=PURCHASE_DATE,
                end_date=date(2033, 10, 15),
                km_limit=200_000,
                oem_status=WarrantyStatus.ACTIVE,
            )
        )
        session.commit()
    return vehicle


def add_rules(session: Session, model_id: str = MODEL_ID) -> None:
    """VF6 milestones: 12,000 km / 12 months and 24,000 km / 24 months."""
    rows = [
        (12_000, 12, "BRAKE_INSPECTION", "Brake system inspection", False),
        (12_000, 12, "BATTERY_CHECK", "High-voltage battery check", True),
        (24_000, 24, "BRAKE_FLUID", "Replace brake fluid", False),
    ]
    for km, months, code, name, covered in rows:
        session.add(
            MaintenanceRule(
                model_id=model_id,
                odo_milestone=km,
                month_milestone=months,
                item_code=code,
                item_name=name,
                is_covered_by_warranty=covered,
                estimated_cost=100_000,
                estimated_duration_minutes=30,
            )
        )
    session.commit()


def add_odometer(
    session: Session, vehicle: UserVehicle, odo_km: int, recorded_at: datetime = NOW
) -> None:
    session.add(
        VehicleOdometerReading(
            user_vehicle_id=vehicle.id,
            odo_km=odo_km,
            recorded_at=recorded_at,
            oem_data_source="telematics",
            received_via=OemSyncTrigger.POLL,
        )
    )
    session.commit()


def mark_synced(session: Session, vehicle: UserVehicle, at: datetime = NOW) -> None:
    session.add(
        VehicleOemSync(
            user_vehicle_id=vehicle.id,
            usage_synced_at=at,
            service_history_synced_at=at,
            last_attempt_at=at,
        )
    )
    session.commit()


def add_discord_link(
    session: Session,
    user: VehicleUser,
    *,
    status: DiscordLinkStatus = DiscordLinkStatus.ACTIVE,
) -> UserDiscordLink:
    link = UserDiscordLink(
        user_id=user.user_id,
        discord_user_id="1122334455667788990",
        discord_channel_id="1200000000000000001",
        status=status,
        linked_at=NOW,
    )
    session.add(link)
    session.commit()
    return link


# ── Stubs ───────────────────────────────────────────────────────────────────
class StubDataGateway(OemVehicleDataGateway):
    def __init__(
        self,
        *,
        usage: UsageSnapshot | None = None,
        history: list[ServiceHistoryEntry] | None = None,
        usage_error: Exception | None = None,
        history_error: Exception | None = None,
    ) -> None:
        self.usage = usage
        self.history = history or []
        self.usage_error = usage_error
        self.history_error = history_error

    async def get_usage(self, vehicle_id: str) -> UsageSnapshot | None:
        if self.usage_error:
            raise self.usage_error
        return self.usage

    async def get_service_history(self, vehicle_id: str) -> list[ServiceHistoryEntry]:
        if self.history_error:
            raise self.history_error
        return list(self.history)


class MemoryLock(SyncLock):
    def __init__(self) -> None:
        self.held: set[UUID] = set()

    async def acquire(self, user_vehicle_id: UUID) -> bool:
        if user_vehicle_id in self.held:
            return False
        self.held.add(user_vehicle_id)
        return True

    async def release(self, user_vehicle_id: UUID) -> None:
        self.held.discard(user_vehicle_id)


class RecordingScheduler(SyncScheduler):
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, OemSyncTrigger, int]] = []

    def schedule(
        self, user_vehicle_id: UUID, trigger: OemSyncTrigger, *, delay_seconds: int = 0
    ) -> None:
        self.calls.append((user_vehicle_id, trigger, delay_seconds))


class MemoryEventStore(WebhookEventStore):
    def __init__(self) -> None:
        self.events: set[str] = set()
        self.debounced: set[UUID] = set()

    async def claim_event(self, event_id: str) -> bool:
        if event_id in self.events:
            return False
        self.events.add(event_id)
        return True

    async def claim_debounce(self, user_vehicle_id: UUID) -> bool:
        if user_vehicle_id in self.debounced:
            return False
        self.debounced.add(user_vehicle_id)
        return True


__all__ = [
    "OemUnavailableError",
    "OemVehicleNotFoundError",
    "ServiceHistoryEntry",
    "UsageSnapshot",
]
