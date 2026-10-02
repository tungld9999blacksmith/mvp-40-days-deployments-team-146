"""ENT-426 — BookingStatusEvent and ENT-428 — BookingReschedule: append-only booking history.

Columns follow ``docs/specs/sprint-3/entity/us-037-sprint-3-spec.entity.md`` (ENT-426)
and ``docs/specs/sprint-3/entity/us-053-sprint-3-spec.entity.md`` (ENT-428).
Every ``booking.status`` change writes one event in the same transaction
(BR-ENT-490); a reschedule changes the time but not the status, so it is
kept in its own table.
"""

from datetime import date, datetime, time
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, Time, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from .booking import BookingStatus


class BookingActorType(StrEnum):
    VEHICLE_OWNER = "vehicle_owner"
    WORKSHOP_OWNER = "workshop_owner"
    SYSTEM = "system"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


def actor_type_column(server_default: str | None = None) -> Column:
    return Column(
        SQLEnum(BookingActorType, name="booking_actor_type_enum", values_callable=_enum_values),
        nullable=False,
        server_default=server_default,
    )


class BookingStatusEvent(SQLModel, table=True):
    __tablename__ = "booking_status_event"
    __table_args__ = (
        CheckConstraint("from_status IS DISTINCT FROM to_status", name="ck_bse_status_changed"),
        CheckConstraint("to_status <> 'cancelled' OR reason_code IS NOT NULL", name="ck_bse_cancel_reason"),
        CheckConstraint("reason_code IS DISTINCT FROM 'OTHER' OR note IS NOT NULL", name="ck_bse_other_note"),
        CheckConstraint(
            "actor_type <> 'system' OR (actor_user_id IS NULL AND actor_workshop_owner_id IS NULL)",
            name="ck_bse_system_actor",
        ),
        Index("ix_bse_booking_created", "booking_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    booking_id: UUID = Field(sa_column=Column(ForeignKey("booking.id", ondelete="CASCADE"), nullable=False))
    # NULL = the booking was created.
    from_status: BookingStatus | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                BookingStatus,
                name="booking_status_enum",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=True,
        ),
    )
    to_status: BookingStatus = Field(
        sa_column=Column(
            SQLEnum(
                BookingStatus,
                name="booking_status_enum",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
        )
    )
    actor_type: BookingActorType = Field(sa_column=actor_type_column())
    actor_user_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("vehicle_user.user_id", ondelete="SET NULL"), nullable=True),
    )
    actor_workshop_owner_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("workshop_owner.id", ondelete="SET NULL"), nullable=True),
    )
    # CHAT / APP / REMINDER_24H / AUTO_CONFIRM / BOARD / QR_SCAN / JOB_WS_DEADLINE.
    source: str = Field(sa_column=Column(String(32), nullable=False))
    reason_code: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    note: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))


class BookingReschedule(SQLModel, table=True):
    __tablename__ = "booking_reschedule"
    __table_args__ = (
        CheckConstraint(
            "to_date <> from_date OR to_time_slot <> from_time_slot",
            name="ck_booking_reschedule_changed",
        ),
        Index("ix_booking_reschedule_booking_created", "booking_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    booking_id: UUID = Field(sa_column=Column(ForeignKey("booking.id", ondelete="CASCADE"), nullable=False))
    from_date: date = Field(sa_column=Column(Date, nullable=False))
    from_time_slot: time = Field(sa_column=Column(Time, nullable=False))
    to_date: date = Field(sa_column=Column(Date, nullable=False))
    to_time_slot: time = Field(sa_column=Column(Time, nullable=False))
    actor_type: BookingActorType = Field(sa_column=actor_type_column())
    actor_user_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("vehicle_user.user_id", ondelete="SET NULL"), nullable=True),
    )
    # APP / CHAT / REMINDER_24H.
    source: str = Field(sa_column=Column(String(32), nullable=False))
    source_message_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True),
    )

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
