"""ENT-412 — FollowUp: post-service check-in sent after a booking is completed.

Columns and lifecycle follow ``docs/specs/entity/crm/follow_up.entity.md``.
At most one follow-up per booking; it is sent 12 hours after the booking
becomes ``completed`` (Q-412, BR-ENT-421). ``has_issue`` escalates to a
``support_ticket`` (BR-ENT-422).
"""

from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository

FOLLOW_UP_DELAY = timedelta(hours=12)


class FollowUpStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    RESPONDED = "responded"
    CLOSED = "closed"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class FollowUp(SQLModel, table=True):
    __tablename__ = "follow_up"
    __table_args__ = (
        CheckConstraint(
            "status = 'pending' OR sent_at IS NOT NULL OR closed_reason = 'NOT_ELIGIBLE'",
            name="ck_follow_up_sent_at",
        ),
        CheckConstraint(
            "status <> 'responded' OR (responded_at IS NOT NULL AND rating IS NOT NULL)",
            name="ck_follow_up_responded",
        ),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_follow_up_rating"),
        CheckConstraint(
            "(status = 'closed') = (closed_reason IS NOT NULL AND closed_at IS NOT NULL)",
            name="ck_follow_up_closed",
        ),
        CheckConstraint(
            "classification_confidence IS NULL OR classification_confidence BETWEEN 0 AND 1",
            name="ck_follow_up_confidence",
        ),
        CheckConstraint(
            "closed_reason IS DISTINCT FROM 'PROCESSED' "
            "OR (rating IS NOT NULL AND responded_at IS NOT NULL AND classified_by IS NOT NULL)",
            name="ck_follow_up_processed",
        ),
        Index(
            "ix_follow_up_sent_sent_at",
            "sent_at",
            postgresql_where=text("status = 'sent'"),
        ),
        Index(
            "ix_follow_up_pending_scheduled",
            "scheduled_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    booking_id: UUID = Field(
        sa_column=Column(ForeignKey("booking.id", ondelete="CASCADE"), nullable=False, unique=True)
    )
    message: str = Field(sa_column=Column(Text, nullable=False))
    customer_response: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    has_issue: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    status: FollowUpStatus = Field(
        default=FollowUpStatus.PENDING,
        sa_column=Column(
            SQLEnum(FollowUpStatus, name="follow_up_status_enum", values_callable=_enum_values),
            nullable=False,
            server_default="pending",
        ),
    )
    # When the follow-up is due: booking completion time + FOLLOW_UP_DELAY.
    scheduled_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    sent_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    responded_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # us-041 extension: answer, classification and closing.
    rating: int | None = Field(default=None, sa_column=Column(SmallInteger, nullable=True))
    feedback_intent: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    classification_confidence: Decimal | None = Field(default=None, sa_column=Column(Numeric(3, 2), nullable=True))
    # RULES / LLM / LLM_FALLBACK.
    classified_by: str | None = Field(default=None, sa_column=Column(String(16), nullable=True))
    # PROCESSED / NO_RESPONSE / NOT_ELIGIBLE.
    closed_reason: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    closed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class FollowUpRepository(SQLModelRepository[FollowUp, UUID]):
    model = FollowUp
