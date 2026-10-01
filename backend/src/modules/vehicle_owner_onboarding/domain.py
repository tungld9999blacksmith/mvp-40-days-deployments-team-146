"""Onboarding module — domain layer.

Contains:
    - Enums shared by the onboarding tables and the API.
    - SQLModel tables for the onboarding-specific entities (ENT-002, ENT-004..ENT-006).
      ``VehicleUser`` (ENT-001) and ``UserVehicle`` (ENT-003) are core entities
      and live in ``common/core``; they are re-exported here for convenience.
    - Pure business helpers (next-step / expiry computation, normalization).

Rules:
    - No FastAPI, no Session, no external SDK here.
    - Enum values are stored lowercase in the DB; the API maps them to
      UPPER_SNAKE_CASE via ``enum.name`` (see schemas.py).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlmodel import Field, SQLModel

from src.common.core.identity.vehicle_user import OnboardingStatus, UserStatus
from src.common.core.vehicle.user_vehicle import (
    UserVehicle,
    VehicleLinkStatus,
    VehicleVerificationStatus,
    VerificationFailureReason,
)

__all__ = [
    "OnboardingStatus",
    "UserStatus",
    "VehicleVerificationStatus",
    "VehicleLinkStatus",
    "VerificationAttemptStatus",
    "VerificationFailureReason",
    "LocationType",
    "LocationSource",
    "ConsentType",
    "WarrantyComponent",
    "WarrantyStatus",
    "NextStep",
    "UserLocation",
    "UserVehicle",
    "VehicleWarranty",
    "VehicleVerificationAttempt",
    "UserConsent",
    "compute_next_step",
    "compute_expires_at",
    "normalize_phone",
]


# ---------------------------------------------------------------------------
# Enums (DB stores the lowercase value)
# ---------------------------------------------------------------------------
class VerificationAttemptStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class LocationType(str, Enum):
    HOME = "home"
    WORK = "work"
    OTHER = "other"


class LocationSource(str, Enum):
    MANUAL = "manual"
    MAP_PICK = "map_pick"
    GPS = "gps"


class ConsentType(str, Enum):
    PERSONAL_DATA_PROCESSING = "personal_data_processing"
    OEM_DATA_SHARING = "oem_data_sharing"


class WarrantyComponent(str, Enum):
    BATTERY = "battery"
    MOTOR = "motor"
    CHASSIS = "chassis"
    ELECTRONICS = "electronics"


class WarrantyStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"


class NextStep(str, Enum):
    """Screen the frontend should route to after each onboarding call."""

    PROFILE = "PROFILE"
    VEHICLE = "VEHICLE"
    VERIFYING = "VERIFYING"
    HOME = "HOME"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
class UserLocation(SQLModel, table=True):
    """ENT-002 — the user's primary nearby location (for workshop suggestions)."""

    __tablename__ = "user_location"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    location_type: LocationType = Field(
        default=LocationType.HOME,
        sa_column=Column(
            SQLEnum(LocationType, name="location_type_enum", values_callable=_enum_values),
            nullable=False,
            server_default="home",
        ),
    )
    address_line: str = Field(sa_column=Column(String(500), nullable=False))
    ward: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    district: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    province: str = Field(sa_column=Column(String(100), nullable=False))
    latitude: Decimal | None = Field(default=None, sa_column=Column(Numeric(9, 6), nullable=True))
    longitude: Decimal | None = Field(default=None, sa_column=Column(Numeric(9, 6), nullable=True))
    source: LocationSource = Field(
        default=LocationSource.MANUAL,
        sa_column=Column(
            SQLEnum(LocationSource, name="location_source_enum", values_callable=_enum_values),
            nullable=False,
            server_default="manual",
        ),
    )
    place_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    is_primary: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default="true")
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class VehicleWarranty(SQLModel, table=True):
    """ENT-004 — warranty contracts synced from the manufacturer."""

    __tablename__ = "vehicle_warranty"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_vehicle_id: UUID = Field(
        sa_column=Column(
            ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    external_warranty_id: str = Field(sa_column=Column(String(64), nullable=False))
    external_policy_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    component: WarrantyComponent = Field(
        sa_column=Column(
            SQLEnum(WarrantyComponent, name="warranty_component_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    start_date: date = Field(sa_column=Column(Date, nullable=False))
    end_date: date = Field(sa_column=Column(Date, nullable=False))
    km_limit: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    duration_months: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    terms_description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    oem_status: WarrantyStatus = Field(
        sa_column=Column(
            SQLEnum(WarrantyStatus, name="warranty_status_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    synced_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class VehicleVerificationAttempt(SQLModel, table=True):
    """ENT-005 — one record per verification submission (retry / idempotency / audit)."""

    __tablename__ = "vehicle_verification_attempt"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    user_vehicle_id: UUID = Field(
        sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False)
    )
    vin: str = Field(sa_column=Column(String(17), nullable=False))
    license_plate: str = Field(sa_column=Column(String(20), nullable=False))
    declared_model_id: str = Field(sa_column=Column(String(64), nullable=False))
    status: VerificationAttemptStatus = Field(
        default=VerificationAttemptStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                VerificationAttemptStatus,
                name="verification_attempt_status_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="pending",
        ),
    )
    failure_reason: VerificationFailureReason | None = Field(
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
    oem_http_status: int | None = Field(default=None, sa_column=Column(SmallInteger, nullable=True))
    oem_request_id: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    retry_count: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0"))
    idempotency_key: str = Field(sa_column=Column(String(128), nullable=False))
    request_hash: str = Field(sa_column=Column(String(64), nullable=False))
    trace_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    requested_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    )
    responded_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    latency_ms: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))


class UserConsent(SQLModel, table=True):
    """ENT-006 — append-only record of consent grants / withdrawals."""

    __tablename__ = "user_consent"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    consent_type: ConsentType = Field(
        sa_column=Column(
            SQLEnum(ConsentType, name="consent_type_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    policy_version: str = Field(sa_column=Column(String(20), nullable=False))
    granted: bool = Field(sa_column=Column(Boolean, nullable=False))
    ip_address: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    user_agent: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


# ---------------------------------------------------------------------------
# Pure business helpers
# ---------------------------------------------------------------------------
def compute_next_step(status: OnboardingStatus, profile_completed: bool) -> NextStep:
    """Decide which screen the frontend should show next (Entity Spec §8.4)."""
    if status == OnboardingStatus.ACTIVE:
        return NextStep.HOME
    if status == OnboardingStatus.PENDING_VEHICLE_VERIFICATION:
        return NextStep.VERIFYING
    if not profile_completed:
        return NextStep.PROFILE
    return NextStep.VEHICLE


def compute_expires_at(
    created_at: datetime,
    status: OnboardingStatus,
    retention_days: int,
) -> datetime | None:
    """When an unfinished onboarding will be purged; None once ACTIVE (D-04)."""
    if status == OnboardingStatus.ACTIVE:
        return None
    return created_at + timedelta(days=retention_days)


_VN_PHONE_RE = re.compile(r"^(0|\+84)(3|5|7|8|9)[0-9]{8}$")


def normalize_phone(raw: str) -> str:
    """Normalize a Vietnamese mobile number to E.164 (+84...).

    Raises ValueError if the number is not a valid VN mobile number.
    """
    cleaned = re.sub(r"[\s.\-]", "", raw)
    if not _VN_PHONE_RE.match(cleaned):
        raise ValueError("invalid Vietnamese mobile phone number")
    if cleaned.startswith("0"):
        cleaned = "+84" + cleaned[1:]
    return cleaned
