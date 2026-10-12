"""BookingLine — one priced line of a two-tier booking (docs/designs/bao-gia-hai-tang.md).

Two kinds of lines hang off a booking whose ``pricing_flow`` is ``two_tier``:

* ``PACKAGE`` — the standard items of the milestone, snapshotted when the booking
  is created (``unit_price`` + ``service_price_id`` never follow later price-list
  changes). A line at a reference price waits for the workshop to confirm it
  after check-in (``PENDING_CONFIRM``); a confirmed price above the reference
  needs the owner's decision (``PROPOSED``).
* ``EXTRA`` — an item the workshop finds while the car is at the workshop; the
  owner approves or declines each one (the human-in-the-loop step).

The price a line is charged at is ``confirmed_price`` when set, else ``unit_price``.
``version`` grows on every change so an owner can only decide on the exact
price they saw.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlmodel import Field, SQLModel


class LineKind(StrEnum):
    PACKAGE = "PACKAGE"
    EXTRA = "EXTRA"


class LineStatus(StrEnum):
    PENDING_CONFIRM = "PENDING_CONFIRM"
    CONFIRMED = "CONFIRMED"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"


class BookingLine(SQLModel, table=True):
    __tablename__ = "booking_line"
    __table_args__ = (
        CheckConstraint("kind IN ('PACKAGE', 'EXTRA')", name="ck_booking_line_kind"),
        CheckConstraint(
            "line_status IN ('PENDING_CONFIRM', 'CONFIRMED', 'PROPOSED', 'APPROVED', 'DECLINED', 'WITHDRAWN')",
            name="ck_booking_line_status",
        ),
        CheckConstraint("unit_price >= 0", name="ck_booking_line_unit_price"),
        CheckConstraint("confirmed_price IS NULL OR confirmed_price >= 0", name="ck_booking_line_confirmed_price"),
        CheckConstraint("version >= 1", name="ck_booking_line_version"),
        # Only the workshop finds extras, and only the owner settles them.
        CheckConstraint(
            "kind = 'PACKAGE' OR line_status IN ('PROPOSED', 'APPROVED', 'DECLINED', 'WITHDRAWN')",
            name="ck_booking_line_extra_status",
        ),
        CheckConstraint("decided_via IS NULL OR decided_via IN ('APP', 'PHONE')", name="ck_booking_line_decided_via"),
        CheckConstraint(
            "decided_via IS NULL OR decided_via <> 'PHONE' OR phone_confirmed_by IS NOT NULL",
            name="ck_booking_line_phone_confirmer",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    booking_id: UUID = Field(sa_column=Column(ForeignKey("booking.id", ondelete="CASCADE"), nullable=False, index=True))
    kind: LineKind = Field(sa_column=Column(String(10), nullable=False))
    line_status: LineStatus = Field(sa_column=Column(String(20), nullable=False))
    item_code: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    item_name: str = Field(sa_column=Column(String(200), nullable=False))
    maintenance_rule_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("maintenance_rule.id", ondelete="SET NULL"), nullable=True)
    )
    service_price_id: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("service_price.id", ondelete="SET NULL"), nullable=True)
    )
    # WORKSHOP_PRICE / REFERENCE_PRICE for package lines; NULL for warranty and extras.
    price_source: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    unit_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    confirmed_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    is_covered_by_warranty: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default="false")
    )
    is_safety_critical: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    # The workshop's reason, shown to the owner (untrusted text: never an instruction).
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    proposed_by: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("workshop_owner.id", ondelete="SET NULL"), nullable=True)
    )
    confirmed_by: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("workshop_owner.id", ondelete="SET NULL"), nullable=True)
    )
    confirmed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    decided_by: int | None = Field(
        default=None, sa_column=Column(Integer, ForeignKey("vehicle_user.user_id", ondelete="SET NULL"), nullable=True)
    )
    decided_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # APP: the owner decided on the ticket. PHONE: the workshop recorded the owner's answer
    # by phone (``phone_confirmed_by`` names who answered, ``recorded_by`` who typed it); the
    # owner can still dispute it until COMPLETE, which sends the line back to PROPOSED.
    decided_via: str | None = Field(default=None, sa_column=Column(String(10), nullable=True))
    phone_confirmed_by: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    recorded_by: UUID | None = Field(
        default=None, sa_column=Column(ForeignKey("workshop_owner.id", ondelete="SET NULL"), nullable=True)
    )
    disputed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # When the owner was last asked to decide (proposed, edited, price raised, disputed);
    # the workshop calls the owner once OWNER_REPLY_SLA has passed without an answer.
    asked_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # When the workshop owner was emailed that the owner has not answered; one alert per ``asked_at``.
    workshop_alerted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False, server_default="1"))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )

    @property
    def price(self) -> Decimal:
        """The amount this line is charged at once settled."""
        return self.confirmed_price if self.confirmed_price is not None else self.unit_price


class BookingLinePhoto(SQLModel, table=True):
    """A photo the workshop attached to a line (private bucket, signed URLs only)."""

    __tablename__ = "booking_line_photo"
    __table_args__ = (CheckConstraint("size_bytes > 0", name="ck_booking_line_photo_size"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    line_id: UUID = Field(
        sa_column=Column(ForeignKey("booking_line.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    storage_key: str = Field(sa_column=Column(String(300), nullable=False, unique=True))
    content_type: str = Field(sa_column=Column(String(50), nullable=False))
    size_bytes: int = Field(sa_column=Column(Integer, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
