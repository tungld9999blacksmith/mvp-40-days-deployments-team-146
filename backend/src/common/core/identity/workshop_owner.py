"""ENT-007 — WorkshopOwner: the Workshop Portal account of a workshop manager.

Kept in ``common/core`` (like ``VehicleUser``) because it is shared by the
workshop-owner onboarding module and the workshop-owner auth module.

It is deliberately a separate table from ``vehicle_user`` (W-04): the same
Gmail / national id may exist in both tables as two independent accounts.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository

from .vehicle_user import UserStatus


class WorkshopOwnerOnboardingStatus(str, Enum):
    """Where the workshop owner is in onboarding (FF FEAT-AUTH-003 §13)."""

    ONBOARDING_IN_PROGRESS = "onboarding_in_progress"
    PENDING_WORKSHOP_VERIFICATION = "pending_workshop_verification"
    VERIFICATION_FAILED = "verification_failed"
    ACTIVE = "active"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist the lowercase ``value`` of each member (not its name)."""
    return [member.value for member in enum_cls]


class WorkshopOwner(SQLModel, table=True):
    __tablename__ = "workshop_owner"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # ── Identity (from Firebase / Google) ────────────────────────────
    firebase_uid: str = Field(
        sa_column=Column(String(128), unique=True, index=True, nullable=False)
    )

    # Also the manager email the manufacturer matches against (W-01).
    email: str = Field(
        sa_column=Column(String(255), unique=True, index=True, nullable=False)
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
        default=None, sa_column=Column(String(255), nullable=True)
    )

    avatar_url: str | None = Field(
        default=None, sa_column=Column(String(1024), nullable=True)
    )

    # ── Profile (entered during onboarding) ──────────────────────────
    full_name: str | None = Field(
        default=None, sa_column=Column(String(150), nullable=True)
    )

    phone: str | None = Field(
        default=None,
        sa_column=Column(String(20), unique=True, index=True, nullable=True),
    )

    # Second verification factor sent to the manufacturer (W-01).
    national_id: str | None = Field(
        default=None,
        sa_column=Column(String(12), unique=True, index=True, nullable=True),
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

    onboarding_status: WorkshopOwnerOnboardingStatus = Field(
        default=WorkshopOwnerOnboardingStatus.ONBOARDING_IN_PROGRESS,
        sa_column=Column(
            SQLEnum(
                WorkshopOwnerOnboardingStatus,
                name="workshop_owner_onboarding_status_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="onboarding_in_progress",
        ),
    )

    # ── Timestamps ────────────────────────────────────────────────────
    profile_completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    onboarding_completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    last_login_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    last_logout_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
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


class WorkshopOwnerRepository(SQLModelRepository[WorkshopOwner, UUID]):
    model = WorkshopOwner
