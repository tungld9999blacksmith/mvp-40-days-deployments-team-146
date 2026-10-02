"""ENT-416 — VehicleOemSync: per-vehicle state of the manufacturer data sync.

Columns follow ``docs/specs/sprint-2/entity/us-017-sprint-2-spec.entity.md``.
Distinguishes "never synced" from "synced, manufacturer has no history"
(BR-ENT-436) and tracks consecutive failures for alerting (BR-ENT-437).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository

from .vehicle_odometer_reading import OemSyncTrigger, _enum_values


class VehicleOemSync(SQLModel, table=True):
    __tablename__ = "vehicle_oem_sync"
    __table_args__ = (CheckConstraint("consecutive_failures >= 0", name="ck_oem_sync_failures"),)

    user_vehicle_id: UUID = Field(
        sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    )
    usage_synced_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    service_history_synced_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_attempt_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    last_trigger: OemSyncTrigger | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                OemSyncTrigger,
                name="oem_sync_trigger_enum",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=True,
        ),
    )
    last_error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    consecutive_failures: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class VehicleOemSyncRepository(SQLModelRepository[VehicleOemSync, UUID]):
    model = VehicleOemSync
