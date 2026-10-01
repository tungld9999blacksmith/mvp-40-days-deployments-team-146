"""ENT-414 — VehicleOdometerReading: odometer values synced from the manufacturer.

Columns follow ``docs/specs/sprint-2/entity/us-017-sprint-2-spec.entity.md``.
Append-only: one row per manufacturer snapshot (``VehicleUsage``). Vehicle
owners never write odometer values (FEAT-VEH-001 BR-003).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class OemUsageSource(str, Enum):
    """How the manufacturer collected the value (``VehicleUsage.data_source``)."""

    TELEMATICS = "telematics"
    MANUAL = "manual"


class OemSyncTrigger(str, Enum):
    """What started the sync that stored the value."""

    POLL = "poll"
    WEBHOOK = "webhook"
    INITIAL = "initial"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class VehicleOdometerReading(SQLModel, table=True):
    __tablename__ = "vehicle_odometer_reading"
    __table_args__ = (
        CheckConstraint("odo_km BETWEEN 0 AND 999999", name="ck_odometer_odo_km"),
        UniqueConstraint(
            "user_vehicle_id", "recorded_at", name="ux_odometer_vehicle_recorded_at"
        ),
        Index("ix_odometer_vehicle_odo", "user_vehicle_id", "odo_km", "recorded_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_vehicle_id: UUID = Field(
        sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False)
    )
    odo_km: int = Field(sa_column=Column(Integer, nullable=False))
    recorded_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    oem_data_source: OemUsageSource = Field(
        sa_column=Column(
            SQLEnum(OemUsageSource, name="oem_usage_source_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    received_via: OemSyncTrigger = Field(
        sa_column=Column(
            SQLEnum(OemSyncTrigger, name="oem_sync_trigger_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class VehicleOdometerReadingRepository(SQLModelRepository[VehicleOdometerReading, UUID]):
    model = VehicleOdometerReading
