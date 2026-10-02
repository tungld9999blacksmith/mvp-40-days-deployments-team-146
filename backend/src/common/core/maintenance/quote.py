"""ENT-410 — Quote: a maintenance quote for one vehicle at one workshop (HITL).

Columns and lifecycle follow ``docs/specs/entity/maintenance/quote.entity.md``.
The AI Agent drafts the quote; the workshop owner approves or rejects it
(Q-411). Only an ``approved`` quote that has not passed ``expires_at`` can be
attached to a booking (BR-ENT-426).
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class QuoteStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Quote(SQLModel, table=True):
    __tablename__ = "quote"
    __table_args__ = (
        CheckConstraint("estimated_total >= 0", name="ck_quote_estimated_total"),
        CheckConstraint("approved_total IS NULL OR approved_total >= 0", name="ck_quote_approved_total"),
        CheckConstraint("odo_milestone IS NULL OR odo_milestone > 0", name="ck_quote_odo_milestone"),
        CheckConstraint(
            "status NOT IN ('approved', 'rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_quote_reviewed",
        ),
        CheckConstraint(
            "status <> 'approved' OR (approved_total IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_quote_approved_fields",
        ),
        CheckConstraint(
            "expires_at IS NULL OR (reviewed_at IS NOT NULL AND expires_at > reviewed_at)",
            name="ck_quote_expires_after_review",
        ),
        CheckConstraint("booking_id IS NULL OR status = 'approved'", name="ck_quote_booking_requires_approval"),
        CheckConstraint("status = 'draft' OR submitted_at IS NOT NULL", name="ck_quote_submitted_at"),
        CheckConstraint(
            "reviewed_at IS NULL OR submitted_at IS NULL OR reviewed_at >= submitted_at",
            name="ck_quote_reviewed_after_submit",
        ),
        # BR-ENT-1102 — one pending quote per (vehicle, workshop, milestone).
        Index(
            "uq_quote_pending_per_milestone",
            "user_vehicle_id",
            "workshop_id",
            "odo_milestone",
            unique=True,
            postgresql_where=text("status = 'pending_approval'"),
            sqlite_where=text("status = 'pending_approval'"),
        ),
        Index("ix_quote_workshop_status", "workshop_id", "status"),
        Index("ix_quote_user_vehicle_created", "user_vehicle_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_vehicle_id: UUID = Field(sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False))
    workshop_id: UUID = Field(sa_column=Column(ForeignKey("workshop.id"), nullable=False))
    # Milestone this quote is for (matches ``maintenance_rule.odo_milestone``);
    # NULL for ad-hoc quotes outside the maintenance schedule.
    odo_milestone: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    # Set only when an approved quote is used to create a booking.
    booking_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("booking.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    # Chat message that requested this quote, when drafted from chat (BR-ENT-460).
    source_message_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True),
    )
    status: QuoteStatus = Field(
        default=QuoteStatus.DRAFT,
        sa_column=Column(
            SQLEnum(QuoteStatus, name="quote_status_enum", values_callable=_enum_values),
            nullable=False,
            server_default="draft",
        ),
    )
    estimated_total: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    approved_total: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    # Reviewer is the owner of ``workshop_id`` (BR-ENT-413).
    reviewed_by: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("workshop_owner.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    reviewer_note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    reviewed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # draft -> pending_approval moment (us-049 BR-1103).
    submitted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # Owner opened the reviewed quote — drives the "result" badge (us-049 BR-1109).
    result_seen_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class QuoteRepository(SQLModelRepository[Quote, UUID]):
    model = Quote
