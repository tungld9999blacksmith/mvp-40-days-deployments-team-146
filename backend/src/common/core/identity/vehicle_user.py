"""ENT-001 — VehicleUser: the account of a vehicle owner.

Columns follow ``docs/specs/entity/identity/vehicle_user.entity.md``.
"""

from datetime import date, datetime
from enum import Enum, StrEnum
from uuid import UUID

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class UserStatus(StrEnum):
    """Administrative account state (independent of onboarding)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class OnboardingStatus(StrEnum):
    """Where the user is in the registration / onboarding flow (FF section 13)."""

    ONBOARDING_IN_PROGRESS = "onboarding_in_progress"
    PENDING_VEHICLE_VERIFICATION = "pending_vehicle_verification"
    VERIFICATION_FAILED = "verification_failed"
    ACTIVE = "active"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist the lowercase ``value`` of each member (not its name)."""
    return [member.value for member in enum_cls]


class VehicleUser(SQLModel, table=True):
    __tablename__ = "vehicle_user"

    user_id: int | None = Field(default=None, primary_key=True)

    # ── Identity (from Firebase / Google) ────────────────────────────
    firebase_uid: str = Field(sa_column=Column(String(128), unique=True, index=True, nullable=False))

    email: str | None = Field(
        default=None,
        sa_column=Column(String(255), unique=True, index=True, nullable=True),
    )

    email_verified: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )

    auth_provider: str = Field(
        default="google.com",
        sa_column=Column(String(32), nullable=False, server_default="google.com"),
    )

    display_name: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )

    avatar_url: str | None = Field(
        default=None,
        sa_column=Column(String(1024), nullable=True),
    )

    # ── Profile (entered during onboarding) ──────────────────────────
    full_name: str | None = Field(
        default=None,
        sa_column=Column(String(150), nullable=True),
    )

    phone: str | None = Field(
        default=None,
        sa_column=Column(String(20), unique=True, index=True, nullable=True),
    )

    national_id: str | None = Field(
        default=None,
        sa_column=Column(String(12), unique=True, index=True, nullable=True),
    )

    date_of_birth: date | None = Field(
        default=None,
        sa_column=Column(Date, nullable=True),
    )

    # Deprecated: the system authenticates via Google only, no password.
    password_hash: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )

    # ``owner_id`` on the manufacturer side (string, e.g. "OWN-004"),
    # assigned once the first vehicle is verified.
    external_owner_id: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
    )

    # Default workshop suggested when booking (AF-001).
    preferred_workshop_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("workshop.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    # ── State ─────────────────────────────────────────────────────────
    status: UserStatus = Field(
        default=UserStatus.ACTIVE,
        sa_column=Column(
            SQLEnum(UserStatus, name="user_status_enum", values_callable=_enum_values),
            nullable=False,
            server_default="active",
        ),
    )

    onboarding_status: OnboardingStatus = Field(
        default=OnboardingStatus.ONBOARDING_IN_PROGRESS,
        sa_column=Column(
            SQLEnum(
                OnboardingStatus,
                name="onboarding_status_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="onboarding_in_progress",
        ),
    )

    # ── Timestamps ────────────────────────────────────────────────────
    profile_completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    onboarding_completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )

    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )

    last_login_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    # Set when the user actively signs out (FEAT-AUTH-002, ENT-101).
    last_logout_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class VehicleUserRepository(SQLModelRepository[VehicleUser, int]):
    model = VehicleUser
