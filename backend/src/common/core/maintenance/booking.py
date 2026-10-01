"""ENT-402 — Booking: a maintenance appointment between a vehicle owner and a workshop.

Columns and status lifecycle follow ``docs/specs/entity/maintenance/booking.entity.md``.
"""

from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Booking(SQLModel, table=True):
    __tablename__ = "booking"
    __table_args__ = (
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0", name="ck_booking_estimated_cost"
        ),
        CheckConstraint("actual_cost IS NULL OR actual_cost >= 0", name="ck_booking_actual_cost"),
        CheckConstraint(
            "odo_milestone IS NULL OR odo_milestone > 0", name="ck_booking_odo_milestone"
        ),
        CheckConstraint("reschedule_count >= 0", name="ck_booking_reschedule_count"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    booking_code: str = Field(
        sa_column=Column(String(20), unique=True, index=True, nullable=False)
    )
    user_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("vehicle_user.user_id"), nullable=False, index=True
        )
    )
    user_vehicle_id: UUID = Field(
        sa_column=Column(ForeignKey("user_vehicle.id"), nullable=False, index=True)
    )
    workshop_id: UUID = Field(
        sa_column=Column(ForeignKey("workshop.id"), nullable=False, index=True)
    )
    booking_date: date = Field(sa_column=Column(Date, nullable=False))
    time_slot: time = Field(sa_column=Column(Time, nullable=False))
    estimated_cost: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(12, 2), nullable=True)
    )
    actual_cost: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(12, 2), nullable=True)
    )
    status: BookingStatus = Field(
        default=BookingStatus.PENDING,
        sa_column=Column(
            SQLEnum(BookingStatus, name="booking_status_enum", values_callable=_enum_values),
            nullable=False,
            server_default="pending",
        ),
    )
    # EF-001: a ``pending`` booking past this moment is moved to ``cancelled``.
    hold_expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Owner tapped "I will come" (us-033 BR-708); written once, status unchanged.
    attendance_confirmed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Maintenance milestone of the appointment (us-053 BR-1202); NULL when unknown.
    odo_milestone: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    # Number of owner reschedules so far (us-053 BR-1207).
    reschedule_count: int = Field(
        default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0")
    )
    # Chat message that confirmed this booking, when created from chat (AC-F4-06,
    # BR-ENT-460). NULL when booked from the UI or after the conversation is deleted.
    source_message_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True
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


class BookingRepository(SQLModelRepository[Booking, UUID]):
    model = Booking
