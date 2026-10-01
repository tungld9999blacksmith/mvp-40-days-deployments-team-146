"""Appointment reminders and per-channel delivery results for event notifications.

* ENT-424 ``booking_reminder`` / ENT-425 ``booking_reminder_delivery`` —
  ``docs/specs/sprint-3/entity/us-033-sprint-3-spec.entity.md``.
* ``follow_up_delivery`` — ``docs/specs/sprint-4/entity/us-041-sprint-4-spec.entity.md``.

Message bodies and recipient addresses are never stored (BR-ENT-487).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.core.maintenance.reminder import ReminderChannel, _enum_values

from .reminder_delivery import DeliveryStatus


class BookingReminderKind(str, Enum):
    BEFORE_24H = "before_24h"


class BookingReminderStatus(str, Enum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


def _channel_column() -> Column:
    return Column(
        SQLEnum(
            ReminderChannel,
            name="reminder_channel_enum",
            values_callable=_enum_values,
            create_type=False,
        ),
        nullable=False,
    )


def _delivery_status_column() -> Column:
    return Column(
        SQLEnum(
            DeliveryStatus,
            name="notification_delivery_status_enum",
            values_callable=_enum_values,
            create_type=False,
        ),
        nullable=False,
        server_default="pending",
    )


def _ts(nullable: bool = True) -> Column:
    return Column(DateTime(timezone=True), nullable=nullable)


class BookingReminder(SQLModel, table=True):
    __tablename__ = "booking_reminder"
    __table_args__ = (
        UniqueConstraint(
            "booking_id", "kind", "appointment_at", name="ux_booking_reminder_booking_kind_appt"
        ),
        CheckConstraint(
            "scheduled_at < appointment_at", name="ck_booking_reminder_schedule_before_appt"
        ),
        CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL)",
            name="ck_booking_reminder_skip_reason",
        ),
        CheckConstraint(
            "status <> 'sent' OR sent_at IS NOT NULL", name="ck_booking_reminder_sent_at"
        ),
        Index(
            "ix_booking_reminder_due",
            "scheduled_at",
            postgresql_where=text("status = 'scheduled'"),
            sqlite_where=text("status = 'scheduled'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    booking_id: UUID = Field(
        sa_column=Column(ForeignKey("booking.id", ondelete="CASCADE"), nullable=False)
    )
    kind: BookingReminderKind = Field(
        default=BookingReminderKind.BEFORE_24H,
        sa_column=Column(
            SQLEnum(
                BookingReminderKind,
                name="booking_reminder_kind_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="before_24h",
        ),
    )
    # Appointment time when scheduled — detects a later reschedule (BR-707).
    appointment_at: datetime = Field(sa_column=_ts(nullable=False))
    scheduled_at: datetime = Field(sa_column=_ts(nullable=False))
    status: BookingReminderStatus = Field(
        default=BookingReminderStatus.SCHEDULED,
        sa_column=Column(
            SQLEnum(
                BookingReminderStatus,
                name="booking_reminder_status_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="scheduled",
        ),
    )
    # BOOKED_WITHIN_24H / BOOKING_CANCELLED / BOOKING_NOT_CONFIRMED / RESCHEDULED / TOO_LATE.
    skip_reason: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    sent_at: datetime | None = Field(default=None, sa_column=_ts())
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class BookingReminderDelivery(SQLModel, table=True):
    __tablename__ = "booking_reminder_delivery"
    __table_args__ = (
        UniqueConstraint(
            "booking_reminder_id", "channel", name="ux_booking_reminder_delivery_channel"
        ),
        CheckConstraint("attempts >= 0", name="ck_booking_reminder_delivery_attempts"),
        CheckConstraint(
            "status <> 'sent' OR sent_at IS NOT NULL", name="ck_booking_reminder_delivery_sent_at"
        ),
        Index(
            "ix_booking_reminder_delivery_retry",
            "status",
            "attempts",
            postgresql_where=text("status = 'failed'"),
            sqlite_where=text("status = 'failed'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    booking_reminder_id: UUID = Field(
        sa_column=Column(ForeignKey("booking_reminder.id", ondelete="CASCADE"), nullable=False)
    )
    channel: ReminderChannel = Field(sa_column=_channel_column())
    status: DeliveryStatus = Field(default=DeliveryStatus.PENDING, sa_column=_delivery_status_column())
    attempts: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0"))
    last_attempt_at: datetime | None = Field(default=None, sa_column=_ts())
    sent_at: datetime | None = Field(default=None, sa_column=_ts())
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class FollowUpDelivery(SQLModel, table=True):
    __tablename__ = "follow_up_delivery"
    __table_args__ = (
        UniqueConstraint("follow_up_id", "channel", name="ux_follow_up_delivery_channel"),
        CheckConstraint("attempts >= 0", name="ck_follow_up_delivery_attempts"),
        CheckConstraint(
            "status <> 'sent' OR sent_at IS NOT NULL", name="ck_follow_up_delivery_sent_at"
        ),
        Index(
            "ix_follow_up_delivery_retry",
            "status",
            "attempts",
            postgresql_where=text("status = 'failed'"),
            sqlite_where=text("status = 'failed'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    follow_up_id: UUID = Field(
        sa_column=Column(ForeignKey("follow_up.id", ondelete="CASCADE"), nullable=False)
    )
    channel: ReminderChannel = Field(sa_column=_channel_column())
    status: DeliveryStatus = Field(default=DeliveryStatus.PENDING, sa_column=_delivery_status_column())
    attempts: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0"))
    last_attempt_at: datetime | None = Field(default=None, sa_column=_ts())
    sent_at: datetime | None = Field(default=None, sa_column=_ts())
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )
