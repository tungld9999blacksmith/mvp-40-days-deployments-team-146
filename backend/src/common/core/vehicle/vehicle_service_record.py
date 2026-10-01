"""ENT-415 — VehicleServiceRecord: completed maintenance visits of a vehicle.

Columns follow ``docs/specs/sprint-2/entity/us-017-sprint-2-spec.entity.md``.
Two sources: ``oem`` (copy of the manufacturer's ``ServiceHistory``, upserted by
the sync job) and ``ev_care`` (a booking completed on the Workshop Board, F8).
"""

from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
    true,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class ServiceRecordSource(str, Enum):
    OEM = "oem"
    EV_CARE = "ev_care"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class VehicleServiceRecord(SQLModel, table=True):
    __tablename__ = "vehicle_service_record"
    __table_args__ = (
        CheckConstraint(
            "odo_km IS NULL OR odo_km BETWEEN 0 AND 999999", name="ck_service_record_odo_km"
        ),
        CheckConstraint(
            "source <> 'oem' OR external_order_id IS NOT NULL",
            name="ck_service_record_oem_order",
        ),
        CheckConstraint(
            "source = 'oem' OR external_order_id IS NULL",
            name="ck_service_record_order_only_oem",
        ),
        CheckConstraint(
            "source = 'ev_care' OR booking_id IS NULL",
            name="ck_service_record_booking_only_ev_care",
        ),
        Index(
            "ux_service_record_oem_order",
            "user_vehicle_id",
            "external_order_id",
            unique=True,
            postgresql_where=text("source = 'oem'"),
            sqlite_where=text("source = 'oem'"),
        ),
        Index(
            "ux_service_record_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("source = 'ev_care'"),
            sqlite_where=text("source = 'ev_care'"),
        ),
        Index("ix_service_record_vehicle_date", "user_vehicle_id", "service_date", "odo_km"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_vehicle_id: UUID = Field(
        sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False)
    )
    source: ServiceRecordSource = Field(
        sa_column=Column(
            SQLEnum(
                ServiceRecordSource,
                name="service_record_source_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
        )
    )
    external_order_id: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    booking_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("booking.id", ondelete="SET NULL"), nullable=True),
    )
    service_date: date = Field(sa_column=Column(Date, nullable=False))
    odo_km: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    external_center_id: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    workshop_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("workshop.id", ondelete="SET NULL"), nullable=True),
    )
    items_done: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # False = repair outside the periodic schedule; never used as the baseline (Q-304).
    is_periodic: bool = Field(
        default=True, sa_column=Column(Boolean, server_default=true(), nullable=False)
    )
    synced_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class VehicleServiceRecordRepository(SQLModelRepository[VehicleServiceRecord, UUID]):
    model = VehicleServiceRecord
