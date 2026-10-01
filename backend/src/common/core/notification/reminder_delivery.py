"""ENT-420 - ReminderDelivery: the result of sending one reminder through one channel.

Columns follow ``docs/specs/sprint-2/entity/us-021-sprint-2-spec.entity.md``. The
message body and the recipient address are not stored (BR-ENT-455).
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
from src.common.data_access import SQLModelRepository


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    NO_RECIPIENT = "no_recipient"


class ReminderDelivery(SQLModel, table=True):
    __tablename__ = "reminder_delivery"
    __table_args__ = (
        UniqueConstraint("reminder_id", "channel", name="ux_reminder_delivery_reminder_channel"),
        CheckConstraint("attempts >= 0", name="ck_reminder_delivery_attempts"),
        CheckConstraint(
            "status <> 'sent' OR sent_at IS NOT NULL", name="ck_reminder_delivery_sent_at"
        ),
        Index(
            "ix_reminder_delivery_retry",
            "status",
            "attempts",
            postgresql_where=text("status = 'failed'"),
            sqlite_where=text("status = 'failed'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    reminder_id: UUID = Field(
        sa_column=Column(ForeignKey("reminder.id", ondelete="CASCADE"), nullable=False)
    )
    channel: ReminderChannel = Field(
        sa_column=Column(
            SQLEnum(
                ReminderChannel,
                name="reminder_channel_enum",
                values_callable=_enum_values,
                create_type=False,
            ),
            nullable=False,
        )
    )
    status: DeliveryStatus = Field(
        default=DeliveryStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                DeliveryStatus,
                name="notification_delivery_status_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="pending",
        ),
    )
    attempts: int = Field(
        default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0")
    )
    last_attempt_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    sent_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class ReminderDeliveryRepository(SQLModelRepository[ReminderDelivery, UUID]):
    model = ReminderDelivery
