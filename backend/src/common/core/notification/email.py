"""Durable maintenance-email outbox, delivery arbitration and webhook receipts.

Payload/recipient live ONLY in this restricted outbox, not ReminderDelivery.
See section 7 of docs/plans/MAIN_REAL_SERVICES_EMAIL_INTEGRATION_PLAN.md
for access and retention policy.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlmodel import Field, SQLModel


class EmailVehicleGate(SQLModel, table=True):
    __tablename__ = "email_vehicle_gate"
    user_vehicle_id: UUID = Field(sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), primary_key=True))


class EmailOutbox(SQLModel, table=True):
    __tablename__ = "email_outbox"
    delivery_id: UUID = Field(
        sa_column=Column(ForeignKey("reminder_delivery.id", ondelete="CASCADE"), primary_key=True)
    )
    user_id: int = Field(
        sa_column=Column(ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False, index=True)
    )
    user_vehicle_id: UUID = Field(
        sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    mode: str = Field(sa_column=Column(String(16), nullable=False))
    recipient_hash: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    # Frozen exact provider request. Never returned by the real-email API.
    recipient: str | None = Field(default=None, sa_column=Column(String(255)))
    payload: dict | None = Field(default=None, sa_column=Column(JSON))
    provider_message_id: str | None = Field(default=None, sa_column=Column(String(255), unique=True))
    delivery_state: str = Field(default="pending", sa_column=Column(String(32), nullable=False, index=True))
    first_attempt_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    next_attempt_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), index=True))
    retry_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    lease_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    claim_token: str | None = Field(default=None, sa_column=Column(String(36)))
    accepted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class EmailSuppression(SQLModel, table=True):
    __tablename__ = "email_suppression"
    recipient_hash: str = Field(sa_column=Column(String(64), primary_key=True))
    reason: str = Field(sa_column=Column(String(32), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class EmailWebhookEvent(SQLModel, table=True):
    __tablename__ = "email_webhook_event"
    event_id: str = Field(sa_column=Column(String(255), primary_key=True))
    provider_message_id: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    delivery_id: UUID | None = Field(default=None, index=True)
    event_type: str = Field(sa_column=Column(String(64), nullable=False))
    recipient_hash: str | None = Field(default=None, sa_column=Column(String(64)))
    source_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    received_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    applied_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
