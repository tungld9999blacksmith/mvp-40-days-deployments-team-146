"""ENT-418 — WorkshopSlotBlock: technician slots a workshop owner blocks by hand.

Columns follow ``docs/specs/sprint-3/entity/us-029-sprint-3-spec.entity.md``.

A block reduces the available capacity of one ``(workshop, date, time_slot)`` so
bookings made through EV Care never take a slot the workshop reserved for other
channels (phone / walk-in). F6 only *reads* these rows for the capacity formula
(BR-005); creating / editing them belongs to F8 — Workshop Board.
"""

from datetime import date, datetime, time
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class SlotBlockReason(str, Enum):
    PHONE_BOOKING = "phone_booking"
    WALK_IN = "walk_in"
    MAINTENANCE = "maintenance"
    OTHER = "other"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class WorkshopSlotBlock(SQLModel, table=True):
    __tablename__ = "workshop_slot_block"
    __table_args__ = (
        UniqueConstraint(
            "workshop_id", "block_date", "time_slot", name="ux_slot_block_ws_date_slot"
        ),
        CheckConstraint("blocked_count > 0", name="ck_slot_block_count_positive"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workshop_id: UUID = Field(
        sa_column=Column(
            ForeignKey("workshop.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    block_date: date = Field(sa_column=Column(Date, nullable=False))
    time_slot: time = Field(sa_column=Column(Time, nullable=False))
    blocked_count: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default="1")
    )
    reason: SlotBlockReason = Field(
        default=SlotBlockReason.OTHER,
        sa_column=Column(
            SQLEnum(SlotBlockReason, name="slot_block_reason_enum", values_callable=_enum_values),
            nullable=False,
            server_default="other",
        ),
    )
    note: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    created_by: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("workshop_owner.id", ondelete="SET NULL"), nullable=True
        ),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class WorkshopSlotBlockRepository(SQLModelRepository[WorkshopSlotBlock, UUID]):
    model = WorkshopSlotBlock
