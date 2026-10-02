"""ENT-418 - UserNotificationSetting: reminder switch and lead time of a vehicle owner.

Columns follow ``docs/specs/sprint-2/entity/us-021-sprint-2-spec.entity.md``. A row
exists only after the owner saved a preference; without one the defaults apply
(``settings.reminder_default_lead_days``, reminders enabled).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    func,
)
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class UserNotificationSetting(SQLModel, table=True):
    __tablename__ = "user_notification_setting"
    __table_args__ = (CheckConstraint("reminder_lead_days BETWEEN 0 AND 30", name="ck_notification_lead_days"),)

    user_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    reminders_enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default="true"))
    reminder_lead_days: int = Field(default=2, sa_column=Column(SmallInteger, nullable=False, server_default="2"))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class UserNotificationSettingRepository(SQLModelRepository[UserNotificationSetting, int]):
    model = UserNotificationSetting
