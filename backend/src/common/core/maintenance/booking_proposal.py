"""ENT-475 — BookingProposal: a booking suggestion waiting for the owner's confirmation.

Columns follow ``docs/specs/sprint-4/entity/us-061-sprint-4-spec.entity.md``.
The proposal holds the status of the chat card (``chat_message.card`` only keeps
a display snapshot); a booking is created from it only through the confirm
endpoint (us-061 BR-1509).
"""

from datetime import date, datetime, time
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, Time, func, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class BookingProposalStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class ProposalSource(StrEnum):
    QUICK_BOOKING = "QUICK_BOOKING"
    CHAT_AGENT = "CHAT_AGENT"


class SupersededReason(StrEnum):
    NEW_PROPOSAL = "NEW_PROPOSAL"
    REVISED = "REVISED"
    SLOT_FULL = "SLOT_FULL"


class LocationBasis(StrEnum):
    DEVICE = "DEVICE"
    PROFILE = "PROFILE"
    PROVINCE = "PROVINCE"
    NONE = "NONE"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


_OPEN = text("status = 'proposed'")
_HAS_BOOKING = text("booking_id IS NOT NULL")


class BookingProposal(SQLModel, table=True):
    __tablename__ = "booking_proposal"
    __table_args__ = (
        # BR-1508: one waiting proposal per owner.
        Index("ux_booking_proposal_open_per_user", "user_id", unique=True, postgresql_where=_OPEN, sqlite_where=_OPEN),
        # BR-1513: one booking per proposal.
        Index(
            "ux_booking_proposal_booking",
            "booking_id",
            unique=True,
            postgresql_where=_HAS_BOOKING,
            sqlite_where=_HAS_BOOKING,
        ),
        Index("ix_booking_proposal_conversation", "conversation_id", "created_at"),
        CheckConstraint(
            "(status = 'confirmed') = (booking_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_booking_proposal_confirmed",
        ),
        CheckConstraint(
            "(status = 'superseded') = (superseded_reason IS NOT NULL)",
            name="ck_booking_proposal_superseded",
        ),
        CheckConstraint("source IN ('QUICK_BOOKING', 'CHAT_AGENT')", name="ck_booking_proposal_source"),
        CheckConstraint(
            "location_basis IN ('DEVICE', 'PROFILE', 'PROVINCE', 'NONE')",
            name="ck_booking_proposal_location_basis",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False)
    )
    user_vehicle_id: UUID = Field(sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False))
    conversation_id: UUID = Field(sa_column=Column(ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False))
    # The chat message carrying the card; set right after the message is saved.
    message_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True)
    )
    source: str = Field(sa_column=Column(String(16), nullable=False))
    status: BookingProposalStatus = Field(
        default=BookingProposalStatus.PROPOSED,
        sa_column=Column(
            SQLEnum(BookingProposalStatus, name="booking_proposal_status_enum", values_callable=_enum_values),
            nullable=False,
            server_default="proposed",
        ),
    )
    superseded_reason: str | None = Field(default=None, sa_column=Column(String(16), nullable=True))
    odo_milestone: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    # Primary option (the slot a confirm books); never changed after insert (BR-ENT-1503).
    workshop_id: UUID = Field(sa_column=Column(ForeignKey("workshop.id"), nullable=False))
    booking_date: date = Field(sa_column=Column(Date, nullable=False))
    time_slot: time = Field(sa_column=Column(Time, nullable=False))
    # Snapshot ``{"primary": {...}, "alternatives": [...]}`` (entity spec §3).
    options: dict = Field(sa_column=Column(JSONB, nullable=False))
    location_basis: str = Field(sa_column=Column(String(16), nullable=False))
    booking_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("booking.id", ondelete="SET NULL"), nullable=True)
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    confirmed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    closed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class BookingProposalRepository(SQLModelRepository[BookingProposal, UUID]):
    model = BookingProposal
