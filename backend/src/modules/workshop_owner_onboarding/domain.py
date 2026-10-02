"""Workshop-owner onboarding — domain layer (FEAT-AUTH-003).

Contains:
    - Enums of this feature (DB stores lowercase values; the API uses ``.name``).
    - Tables owned by this module: ENT-010 ``WorkshopRegistration``,
      ENT-011 ``WorkshopVerificationAttempt``, ENT-012 ``WorkshopOwnerConsent``.
      ``WorkshopOwner`` and ``Workshop`` live in ``common/core`` (shared).
    - Pure business helpers: next step, expiry, normalization, operating hours.

No FastAPI, no Session, no external SDK here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from src.common.core.identity.workshop_owner import WorkshopOwnerOnboardingStatus

# JSONB on Postgres, plain JSON elsewhere (SQLite in tests).
_JSON = JSON().with_variant(JSONB(), "postgresql")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class WorkshopVerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class AttemptStatus(StrEnum):
    """Same values as the shared PG type ``verification_attempt_status_enum``."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class WorkshopVerificationFailureReason(StrEnum):
    MANAGER_NOT_FOUND = "manager_not_found"
    NATIONAL_ID_MISMATCH = "national_id_mismatch"
    ALREADY_CLAIMED = "already_claimed"
    OEM_UNAVAILABLE = "oem_unavailable"


class ConsentType(StrEnum):
    """Same values as the shared PG type ``consent_type_enum``."""

    PERSONAL_DATA_PROCESSING = "personal_data_processing"
    OEM_DATA_SHARING = "oem_data_sharing"


class WorkshopNextStep(StrEnum):
    PROFILE = "PROFILE"
    WORKSHOP = "WORKSHOP"
    VERIFYING = "VERIFYING"
    DASHBOARD = "DASHBOARD"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
class WorkshopRegistration(SQLModel, table=True):
    """ENT-010 — operating data declared at SCR-203 + verification outcome.

    At most one draft (pending / failed) per owner; a verified row is kept as
    history and points to the workshop it materialized into.
    """

    __tablename__ = "workshop_registration"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(
        sa_column=Column(ForeignKey("workshop_owner.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    address: str = Field(sa_column=Column(Text, nullable=False))
    latitude: Decimal | None = Field(default=None, sa_column=Column(Numeric(9, 6), nullable=True))
    longitude: Decimal | None = Field(default=None, sa_column=Column(Numeric(9, 6), nullable=True))
    hotline: str = Field(sa_column=Column(String(20), nullable=False))
    total_technicians: int = Field(sa_column=Column(Integer, nullable=False))
    emergency_slots_reserved: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    # [{"dayOfWeek": 1, "isClosed": false, "openTime": "08:00", "closeTime": "17:30"}, ...]
    operating_hours: list = Field(default_factory=list, sa_column=Column(_JSON, nullable=False))
    verification_status: WorkshopVerificationStatus = Field(
        default=WorkshopVerificationStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                WorkshopVerificationStatus,
                name="workshop_verification_status_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="pending",
        ),
    )
    verification_failure_reason: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    external_center_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    workshop_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("workshop.id", ondelete="SET NULL"), nullable=True),
    )
    verified_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class WorkshopVerificationAttempt(SQLModel, table=True):
    """ENT-011 — one row per "Gửi xác thực" click (retry / idempotency / audit).

    Background retries after an OEM timeout bump ``retry_count`` instead of
    creating a new row. Never stores the national id that was sent.
    """

    __tablename__ = "workshop_verification_attempt"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(
        sa_column=Column(ForeignKey("workshop_owner.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    registration_id: UUID = Field(
        sa_column=Column(ForeignKey("workshop_registration.id", ondelete="CASCADE"), nullable=False)
    )
    status: AttemptStatus = Field(
        default=AttemptStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                AttemptStatus,
                name="verification_attempt_status_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="pending",
        ),
    )
    failure_reason: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    external_center_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    oem_http_status: int | None = Field(default=None, sa_column=Column(SmallInteger, nullable=True))
    oem_request_id: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    retry_count: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0"))
    next_retry_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    idempotency_key: str = Field(sa_column=Column(String(128), nullable=False))
    request_hash: str = Field(sa_column=Column(String(64), nullable=False))
    trace_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    requested_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    )
    responded_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    latency_ms: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))


class WorkshopOwnerConsent(SQLModel, table=True):
    """ENT-012 — append-only consent records of a workshop owner."""

    __tablename__ = "workshop_owner_consent"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(
        sa_column=Column(ForeignKey("workshop_owner.id", ondelete="CASCADE"), nullable=False, index=True)
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
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))


# ---------------------------------------------------------------------------
# Pure business helpers
# ---------------------------------------------------------------------------
def compute_next_step(status: WorkshopOwnerOnboardingStatus, profile_completed: bool) -> WorkshopNextStep:
    """Which screen the portal shows next (Entity Spec ENT-007 §8)."""
    if status == WorkshopOwnerOnboardingStatus.ACTIVE:
        return WorkshopNextStep.DASHBOARD
    if status == WorkshopOwnerOnboardingStatus.PENDING_WORKSHOP_VERIFICATION:
        return WorkshopNextStep.VERIFYING
    if not profile_completed:
        return WorkshopNextStep.PROFILE
    return WorkshopNextStep.WORKSHOP


def compute_expires_at(
    created_at: datetime | None,
    status: WorkshopOwnerOnboardingStatus,
    retention_days: int,
) -> datetime | None:
    """When an unfinished onboarding is purged; ``None`` once ACTIVE (BR-208)."""
    if status == WorkshopOwnerOnboardingStatus.ACTIVE or created_at is None:
        return None
    return created_at + timedelta(days=retention_days)


_SEPARATORS = re.compile(r"[\s.\-]")
_VN_MOBILE_RE = re.compile(r"^(0|\+84)(3|5|7|8|9)[0-9]{8}$")
_HOTLINE_RE = re.compile(r"^((\+84|0)[0-9]{9,10}|(1900|1800)[0-9]{4,6})$")
_NATIONAL_ID_RE = re.compile(r"^[0-9]{12}$")
_HHMM_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def normalize_mobile(raw: str) -> str:
    """VN mobile → E.164 (``+84…``). Raises ValueError if invalid."""
    cleaned = _SEPARATORS.sub("", raw)
    if not _VN_MOBILE_RE.match(cleaned):
        raise ValueError("invalid Vietnamese mobile phone number")
    return "+84" + cleaned[1:] if cleaned.startswith("0") else cleaned


def normalize_hotline(raw: str) -> str:
    """Workshop hotline: mobile → E.164, landline / 1900 / 1800 → digits."""
    cleaned = _SEPARATORS.sub("", raw)
    if not _HOTLINE_RE.match(cleaned):
        raise ValueError("invalid hotline")
    if _VN_MOBILE_RE.match(cleaned):
        return normalize_mobile(cleaned)
    return cleaned


def normalize_national_id(raw: str) -> str:
    """CCCD: keep digits only; must be exactly 12 digits."""
    cleaned = re.sub(r"\s", "", raw)
    if not _NATIONAL_ID_RE.match(cleaned):
        raise ValueError("national id (CCCD) must have 12 digits")
    return cleaned


def mask_national_id(value: str | None) -> str | None:
    """``001190000101`` → ``001******101``."""
    if not value:
        return None
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


@dataclass(frozen=True)
class OperatingHourValue:
    day_of_week: int
    is_closed: bool
    open_time: time | None
    close_time: time | None

    def to_json(self) -> dict:
        return {
            "dayOfWeek": self.day_of_week,
            "isClosed": self.is_closed,
            "openTime": self.open_time.strftime("%H:%M") if self.open_time else None,
            "closeTime": self.close_time.strftime("%H:%M") if self.close_time else None,
        }


class OperatingHoursError(ValueError):
    def __init__(self, message: str, field: str) -> None:
        super().__init__(message)
        self.field = field


def _parse_hhmm(value: str | None, field: str) -> time:
    if value is None or not _HHMM_RE.match(value):
        raise OperatingHoursError("Giờ phải có dạng HH:mm.", field)
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def validate_operating_hours(items: list) -> list[OperatingHourValue]:
    """BR-206: 7 days (ISO 1..7, no duplicates), one range per open day,
    ``close > open``, closed days carry no times, at least one open day.

    ``items`` are objects with ``day_of_week``, ``is_closed``, ``open_time``,
    ``close_time`` (``HH:mm`` strings). Raises ``OperatingHoursError``.
    """
    if len(items) != 7:
        raise OperatingHoursError("Cần khai báo giờ hoạt động cho đủ 7 ngày.", "operatingHours")

    result: list[OperatingHourValue] = []
    seen: set[int] = set()
    for idx, item in enumerate(items):
        prefix = f"operatingHours[{idx}]"
        day = item.day_of_week
        if day < 1 or day > 7 or day in seen:
            raise OperatingHoursError("Ngày trong tuần không hợp lệ hoặc bị trùng.", f"{prefix}.dayOfWeek")
        seen.add(day)

        if item.is_closed:
            if item.open_time is not None or item.close_time is not None:
                raise OperatingHoursError("Ngày đóng cửa không được có giờ mở/đóng.", f"{prefix}.openTime")
            result.append(OperatingHourValue(day, True, None, None))
            continue

        open_t = _parse_hhmm(item.open_time, f"{prefix}.openTime")
        close_t = _parse_hhmm(item.close_time, f"{prefix}.closeTime")
        if close_t <= open_t:
            raise OperatingHoursError("Giờ đóng cửa phải sau giờ mở cửa.", f"{prefix}.closeTime")
        result.append(OperatingHourValue(day, False, open_t, close_t))

    if all(h.is_closed for h in result):
        raise OperatingHoursError("Xưởng phải mở cửa ít nhất 1 ngày trong tuần.", "operatingHours")
    return sorted(result, key=lambda h: h.day_of_week)
