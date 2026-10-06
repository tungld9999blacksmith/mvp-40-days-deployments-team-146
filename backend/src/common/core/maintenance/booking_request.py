"""Durable booking retry receipt, committed atomically with its booking."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlmodel import Field, SQLModel


class BookingRequest(SQLModel, table=True):
    __tablename__ = "booking_request"
    __table_args__ = (
        Index("ux_booking_request_booking", "booking_id", unique=True),
        Index("ix_booking_request_user_id", "user_id"),
    )

    request_id: str = Field(sa_column=Column(String(64), primary_key=True))
    user_id: int = Field(sa_column=Column(Integer, ForeignKey("vehicle_user.user_id"), nullable=False))
    fingerprint: str = Field(sa_column=Column(String(64), nullable=False))
    token_hash: str = Field(sa_column=Column(String(64), nullable=False, unique=True))
    booking_id: UUID = Field(sa_column=Column(ForeignKey("booking.id", ondelete="CASCADE"), nullable=False))
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
