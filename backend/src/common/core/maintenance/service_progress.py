"""ENT-403 — ServiceProgress: append-only stage log of a booking while the car is at the workshop.

Columns follow ``docs/specs/entity/maintenance/service_progress.entity.md``.
"""

from datetime import datetime
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository

from .booking_status_event import BookingActorType, actor_type_column


class ServiceStage(StrEnum):
    CHECKED_IN = "checked_in"
    INSPECTING = "inspecting"
    SERVICING = "servicing"
    WAITING_PARTS = "waiting_parts"
    QUALITY_CHECK = "quality_check"
    READY_FOR_PICKUP = "ready_for_pickup"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class ServiceProgress(SQLModel, table=True):
    __tablename__ = "service_progress"
    __table_args__ = (
        CheckConstraint(
            "actor_type <> 'workshop_owner' OR actor_workshop_owner_id IS NOT NULL",
            name="ck_service_progress_owner_actor",
        ),
        CheckConstraint(
            "stage <> 'waiting_parts' OR length(note) BETWEEN 10 AND 500",
            name="ck_service_progress_waiting_parts_note",
        ),
        Index("ix_service_progress_booking_created", "booking_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    booking_id: UUID = Field(sa_column=Column(ForeignKey("booking.id", ondelete="CASCADE"), nullable=False, index=True))
    stage: ServiceStage = Field(
        sa_column=Column(
            SQLEnum(ServiceStage, name="service_stage_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # Deprecated (us-057) — superseded by ``actor_type`` / ``actor_workshop_owner_id``.
    updated_by: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    actor_type: BookingActorType = Field(
        default=BookingActorType.SYSTEM, sa_column=actor_type_column(server_default="system")
    )
    actor_workshop_owner_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("workshop_owner.id", ondelete="SET NULL"), nullable=True),
    )
    # CHECK_IN / START (hook) or BOARD (workshop owner).
    source: str = Field(default="BOARD", sa_column=Column(String(32), nullable=False, server_default="BOARD"))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))


class ServiceProgressRepository(SQLModelRepository[ServiceProgress, UUID]):
    model = ServiceProgress
