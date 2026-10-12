"""Minimal policy telemetry and confirmed-booking attribution; no ODO traces."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class ReminderPolicyEvaluation(SQLModel, table=True):
    __tablename__ = "reminder_policy_evaluation"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", "evaluation_day", "mode", name="uq_usage_evaluation_vehicle_day_mode"),
        CheckConstraint("duration_ms >= 0", name="ck_usage_evaluation_duration"),
        CheckConstraint("mode IN ('shadow', 'on')", name="ck_usage_evaluation_mode"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(foreign_key="vehicle_user.user_id", index=True)
    user_vehicle_id: UUID = Field(foreign_key="user_vehicle.id", index=True)
    evaluation_day: date = Field(index=True)
    mode: str = Field(sa_column=Column(String(16), nullable=False))
    forecast_status: str = Field(sa_column=Column(String(40), nullable=False))
    baseline_level: str | None = Field(default=None, sa_column=Column(String(16)))
    candidate_level: str | None = Field(default=None, sa_column=Column(String(16)))
    actual_level: str | None = Field(default=None, sa_column=Column(String(16)))
    lead_days: int
    duration_ms: float
    algorithm_version: str = Field(default="usage-v1", sa_column=Column(String(32), nullable=False))
    calculated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))


class ReminderBookingAttribution(SQLModel, table=True):
    __tablename__ = "reminder_booking_attribution"
    __table_args__ = (
        CheckConstraint("match_method IN ('DIRECT', 'RECENT_REMINDER')", name="ck_usage_attribution_method"),
    )

    booking_id: UUID = Field(sa_column=Column(ForeignKey("booking.id", ondelete="CASCADE"), primary_key=True))
    reminder_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("reminder.id", ondelete="SET NULL"), index=True)
    )
    match_method: str = Field(sa_column=Column(String(24), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    confirmed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), index=True))
