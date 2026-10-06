"""ENT-003 — UserVehicle: a vehicle a user declared, plus the manufacturer snapshot.

Columns follow ``docs/specs/entity/vehicle/user_vehicle.entity.md``. Core entity:
bookings and reminders all reference ``user_vehicle``.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class VehicleVerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class VehicleLinkStatus(StrEnum):
    ACTIVE = "active"
    UNLINKED = "unlinked"


class VerificationFailureReason(StrEnum):
    VIN_NOT_FOUND = "vin_not_found"
    PLATE_MISMATCH = "plate_mismatch"
    MODEL_MISMATCH = "model_mismatch"
    OWNER_EMAIL_MISMATCH = "owner_email_mismatch"
    NATIONAL_ID_MISMATCH = "national_id_mismatch"
    ALREADY_LINKED = "already_linked"
    OEM_UNAVAILABLE = "oem_unavailable"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class UserVehicle(SQLModel, table=True):
    """ENT-003 — a vehicle a user declared, plus the manufacturer snapshot."""

    __tablename__ = "user_vehicle"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    # User-declared fields
    vin: str = Field(sa_column=Column(String(17), nullable=False, index=True))
    license_plate: str = Field(sa_column=Column(String(20), nullable=False, index=True))
    declared_model_id: str = Field(sa_column=Column(String(64), nullable=False))
    declared_manufacture_year: int | None = Field(default=None, sa_column=Column(SmallInteger, nullable=True))
    # Manufacturer snapshot (set on verification)
    external_vehicle_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    external_owner_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    external_model_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    model_name: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    trim: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    color: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    manufacture_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    production_year: int | None = Field(default=None, sa_column=Column(SmallInteger, nullable=True))
    battery_capacity_kwh: Decimal | None = Field(default=None, sa_column=Column(Numeric(6, 2), nullable=True))
    motor_power_kw: Decimal | None = Field(default=None, sa_column=Column(Numeric(7, 2), nullable=True))
    # State
    verification_status: VehicleVerificationStatus = Field(
        default=VehicleVerificationStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                VehicleVerificationStatus,
                name="vehicle_verification_status_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="pending",
        ),
    )
    verification_failure_reason: VerificationFailureReason | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                VerificationFailureReason,
                name="verification_failure_reason_enum",
                values_callable=_enum_values,
            ),
            nullable=True,
        ),
    )
    verified_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    link_status: VehicleLinkStatus = Field(
        default=VehicleLinkStatus.ACTIVE,
        sa_column=Column(
            SQLEnum(VehicleLinkStatus, name="vehicle_link_status_enum", values_callable=_enum_values),
            nullable=False,
            server_default="active",
        ),
    )
    oem_synced_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class UserVehicleRepository(SQLModelRepository[UserVehicle, UUID]):
    model = UserVehicle
