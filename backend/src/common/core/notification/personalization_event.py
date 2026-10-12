"""Minimal audit of consent changes; contains no ODO, messages or contacts."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


class ReminderPersonalizationEvent(SQLModel, table=True):
    __tablename__ = "reminder_personalization_event"
    __table_args__ = (
        CheckConstraint("action IN ('GRANTED', 'REVOKED', 'DERIVED_DATA_DELETED')", name="ck_personalization_action"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False, index=True)
    )
    action: str = Field(sa_column=Column(String(32), nullable=False))
    policy_version: str = Field(sa_column=Column(String(64), nullable=False))
    source: str = Field(default="SETTINGS_UI", sa_column=Column(String(32), nullable=False))
    occurred_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
