"""ENT-405 — Reminder: automatic maintenance reminders sent to a vehicle owner.

Columns follow ``docs/specs/entity/maintenance/reminder.entity.md``.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class ReminderLevel(str, Enum):
    EARLY = "early"
    WARNING = "warning"
    URGENT = "urgent"
    EXPIRED = "expired"


class ReminderChannel(str, Enum):
    """Delivery channel (BR-ENT-408).

    Only DISCORD has an adapter today. ZALO / TELEGRAM / SMS / EMAIL are listed
    in the channel settings but cannot be enabled yet (FEAT-NOTI-001 BR-506);
    SLACK is reserved.
    IN_APP / PUSH / SMS_ZALO are deprecated: kept only because PostgreSQL
    cannot drop enum values (migration f6c3a8d1b2e4); never write them.
    """

    DISCORD = "discord"
    EMAIL = "email"
    SMS = "sms"
    TELEGRAM = "telegram"
    ZALO = "zalo"
    SLACK = "slack"
    IN_APP = "in_app"
    PUSH = "push"
    SMS_ZALO = "sms_zalo"



def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Reminder(SQLModel, table=True):
    __tablename__ = "reminder"
    __table_args__ = (
        CheckConstraint("target_odo_milestone > 0", name="ck_reminder_target_odo_milestone"),
        CheckConstraint("snooze_count >= 0", name="ck_reminder_snooze_count"),
        # FEAT-NOTI-001 BR-502: one reminder per (vehicle, milestone, level).
        UniqueConstraint(
            "user_vehicle_id",
            "target_odo_milestone",
            "reminder_level",
            name="ux_reminder_vehicle_milestone_level",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_vehicle_id: UUID = Field(
        sa_column=Column(
            ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    target_odo_milestone: int = Field(sa_column=Column(Integer, nullable=False))
    reminder_level: ReminderLevel = Field(
        default=ReminderLevel.EARLY,
        sa_column=Column(
            SQLEnum(ReminderLevel, name="reminder_level_enum", values_callable=_enum_values),
            nullable=False,
            server_default="early",
        ),
    )
    channel: ReminderChannel = Field(
        default=ReminderChannel.DISCORD,
        sa_column=Column(
            SQLEnum(ReminderChannel, name="reminder_channel_enum", values_callable=_enum_values),
            nullable=False,
            server_default="discord",
        ),
    )
    snooze_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    is_resolved: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default="false")
    )
    scheduled_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class ReminderRepository(SQLModelRepository[Reminder, UUID]):
    model = Reminder
