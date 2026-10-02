"""ENT-411 — QuoteItem: one line of a quote.

Columns follow ``docs/specs/entity/maintenance/quote_item.entity.md``.
``item_code`` / ``item_name`` are snapshots taken when the quote is drafted, so
later changes to ``maintenance_rule`` / ``service_price`` do not alter the quote.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class QuoteItem(SQLModel, table=True):
    __tablename__ = "quote_item"
    __table_args__ = (
        CheckConstraint("estimated_price >= 0", name="ck_quote_item_estimated_price"),
        CheckConstraint("approved_price IS NULL OR approved_price >= 0", name="ck_quote_item_approved_price"),
        # BR-ENT-1101 — a warranty-covered line is locked at 0.
        CheckConstraint(
            "NOT is_covered_by_warranty OR (estimated_price = 0 AND (approved_price IS NULL OR approved_price = 0))",
            name="ck_quote_item_covered_zero",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    quote_id: UUID = Field(sa_column=Column(ForeignKey("quote.id", ondelete="CASCADE"), nullable=False, index=True))
    # NULL for items outside the standard maintenance schedule.
    maintenance_rule_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("maintenance_rule.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    item_code: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    item_name: str = Field(sa_column=Column(String(200), nullable=False))
    estimated_price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    approved_price: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # Snapshot of the estimate line (us-049): warranty flag and price origin.
    is_covered_by_warranty: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default="false")
    )
    # WORKSHOP_PRICE / REFERENCE_PRICE; NULL for covered lines.
    price_source: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    reviewer_note: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class QuoteItemRepository(SQLModelRepository[QuoteItem, UUID]):
    model = QuoteItem
