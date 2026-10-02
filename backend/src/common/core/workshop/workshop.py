"""ENT-008 — Workshop (core table) + ENT-009 WorkshopOperatingHour.

Columns follow ``docs/specs/entity/workshop/workshop.entity.md``; the columns
marked "FEAT-AUTH-003" were added for workshop-owner onboarding. Kept in
``common/core`` because bookings, quotes, prices and vehicle owners reference
workshops too.
"""

from datetime import datetime, time
from decimal import Decimal
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class WorkshopStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ServiceCenterType(StrEnum):
    DEALER = "dealer"
    SERVICE_ONLY = "service_only"


class BookingConfirmationMode(StrEnum):
    """How a held booking becomes a confirmed appointment (F6 BR-014, AI-Q-401).

    ``auto``   — the system confirms right after the owner holds the slot.
    ``manual`` — the workshop owner accepts on the board (F8) before it is confirmed.
    """

    AUTO = "auto"
    MANUAL = "manual"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Workshop(SQLModel, table=True):
    __tablename__ = "workshop"
    __table_args__ = (
        CheckConstraint("total_technicians > 0", name="ck_workshop_total_technicians"),
        CheckConstraint(
            "emergency_slots_reserved >= 0 AND emergency_slots_reserved <= total_technicians",
            name="ck_workshop_emergency_slots",
        ),
        # W-09: an active workshop always has an owner.
        CheckConstraint("status <> 'active' OR owner_id IS NOT NULL", name="ck_workshop_active_has_owner"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # ── From the manufacturer (ServiceCenter) ────────────────────────
    external_center_id: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    name: str = Field(sa_column=Column(String(150), nullable=False))
    region: str = Field(sa_column=Column(String(50), nullable=False))
    type: ServiceCenterType = Field(
        sa_column=Column(
            SQLEnum(
                ServiceCenterType,
                name="service_center_type_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
        )
    )

    # ── Operations (declared by the workshop owner) ──────────────────
    address: str = Field(sa_column=Column(Text, nullable=False))
    total_technicians: int = Field(sa_column=Column(Integer, nullable=False))
    emergency_slots_reserved: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    status: WorkshopStatus = Field(
        default=WorkshopStatus.ACTIVE,
        sa_column=Column(
            SQLEnum(WorkshopStatus, name="workshop_status_enum", values_callable=_enum_values),
            nullable=False,
            server_default="active",
        ),
    )

    # ── FEAT-BOOK-001 (F6 BR-014, AI-Q-401 / Q-405) ──────────────────
    # ``auto`` (default) confirms a held booking immediately; ``manual`` waits
    # for the workshop owner to accept on the board (F8).
    booking_confirmation_mode: BookingConfirmationMode = Field(
        default=BookingConfirmationMode.AUTO,
        sa_column=Column(
            SQLEnum(
                BookingConfirmationMode,
                name="booking_confirmation_mode_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="auto",
        ),
    )

    # ── FEAT-AUTH-003 additions ───────────────────────────────────────
    # One owner ↔ one workshop (W-05): partial unique index in the migration.
    owner_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("workshop_owner.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    hotline: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    latitude: Decimal | None = Field(default=None, sa_column=Column(Numeric(9, 6), nullable=True))
    longitude: Decimal | None = Field(default=None, sa_column=Column(Numeric(9, 6), nullable=True))
    onboarded_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    oem_synced_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class WorkshopOperatingHour(SQLModel, table=True):
    """One row per ISO weekday (1 = Monday … 7 = Sunday), one time range/day."""

    __tablename__ = "workshop_operating_hour"
    __table_args__ = (
        UniqueConstraint("workshop_id", "day_of_week", name="ux_workshop_operating_hour_day"),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_operating_hour_day"),
        CheckConstraint(
            "(is_closed AND open_time IS NULL AND close_time IS NULL) OR "
            "(NOT is_closed AND open_time IS NOT NULL AND close_time IS NOT NULL "
            "AND close_time > open_time)",
            name="ck_operating_hour_range",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workshop_id: UUID = Field(
        sa_column=Column(ForeignKey("workshop.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    day_of_week: int = Field(sa_column=Column(SmallInteger, nullable=False))
    is_closed: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    open_time: time | None = Field(default=None, sa_column=Column(Time, nullable=True))
    close_time: time | None = Field(default=None, sa_column=Column(Time, nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class WorkshopRepository(SQLModelRepository[Workshop, UUID]):
    model = Workshop


class WorkshopOperatingHourRepository(SQLModelRepository[WorkshopOperatingHour, UUID]):
    model = WorkshopOperatingHour
