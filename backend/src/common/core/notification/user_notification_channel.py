"""ENT-419 - UserNotificationChannel: channels an owner turned on or off.

Columns follow ``docs/specs/sprint-2/entity/us-021-sprint-2-spec.entity.md``. No
rows for an owner means the default: Discord only (BR-ENT-451). Recipient
addresses are not stored here; Discord comes from ``user_discord_link``.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.core.maintenance.reminder import ReminderChannel, _enum_values
from src.common.data_access import SQLModelRepository


class UserNotificationChannel(SQLModel, table=True):
    __tablename__ = "user_notification_channel"
    __table_args__ = (UniqueConstraint("user_id", "channel", name="ux_notification_channel_user_channel"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False)
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
    is_enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default="true"))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class UserNotificationChannelRepository(SQLModelRepository[UserNotificationChannel, UUID]):
    model = UserNotificationChannel
