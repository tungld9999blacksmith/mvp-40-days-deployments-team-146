"""Quote module — request/response schemas (us-049 §3-§9)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.common.money import Money


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class QuoteStatusIn(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ── requests ────────────────────────────────────────────────────────────────
class CreateQuoteRequest(CamelModel):
    """Only these fields are read; prices/items from the client are ignored (BR-1101)."""

    user_vehicle_id: UUID
    workshop_id: UUID
    odo_milestone: int = Field(..., gt=0)


class SubmitQuoteRequest(CamelModel):
    confirm: bool = True


class ApproveItemIn(CamelModel):
    quote_item_id: UUID
    approved_price: Decimal = Field(..., ge=0, decimal_places=2)
    note: str | None = Field(default=None, max_length=255)


class ApproveQuoteRequest(CamelModel):
    validity_days: int | None = Field(default=None, ge=1)
    reviewer_note: str | None = Field(default=None, max_length=500)
    items: list[ApproveItemIn] = []


class RejectQuoteRequest(CamelModel):
    reviewer_note: str | None = Field(default=None, max_length=500)


# ── responses ───────────────────────────────────────────────────────────────
class QuoteWorkshopOut(CamelModel):
    workshop_id: UUID
    name: str


class QuoteItemOut(CamelModel):
    quote_item_id: UUID
    item_code: str | None
    item_name: str
    covered: bool
    price_source: str | None
    estimated_price: Money
    approved_price: Money | None
    reviewer_note: str | None


class QuoteOut(CamelModel):
    quote_id: UUID
    status: str
    display_status: str
    price_label: str
    can_attach_to_booking: bool
    user_vehicle_id: UUID
    workshop: QuoteWorkshopOut
    odo_milestone: int | None
    items: list[QuoteItemOut]
    estimated_total: Money
    approved_total: Money | None
    created_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    expires_at: datetime | None
    reviewer_note: str | None
    booking_id: UUID | None


class QuoteEnvelope(CamelModel):
    data: QuoteOut


class QuoteSummaryOut(CamelModel):
    quote_id: UUID
    status: str
    display_status: str
    price_label: str
    can_attach_to_booking: bool
    user_vehicle_id: UUID
    workshop: QuoteWorkshopOut
    odo_milestone: int | None
    estimated_total: Money
    approved_total: Money | None
    created_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    expires_at: datetime | None
    result_seen: bool


class QuoteListData(CamelModel):
    items: list[QuoteSummaryOut]
    next_cursor: str | None = None


class QuoteListEnvelope(CamelModel):
    data: QuoteListData


# ── workshop owner ──────────────────────────────────────────────────────────
class CustomerOut(CamelModel):
    full_name: str | None
    phone: str | None


class WorkshopQuoteItemOut(CamelModel):
    quote_id: UUID
    status: str
    display_status: str
    customer: CustomerOut
    model_name: str | None
    plate_number: str | None
    odo_milestone: int | None
    estimated_total: Money
    approved_total: Money | None
    submitted_at: datetime | None
    waiting_hours: float | None
    is_waiting_long: bool
    has_conversation: bool


class WorkshopQuoteListData(CamelModel):
    items: list[WorkshopQuoteItemOut]
    next_cursor: str | None = None


class WorkshopQuoteListEnvelope(CamelModel):
    data: WorkshopQuoteListData


class WorkshopQuoteOut(QuoteOut):
    customer: CustomerOut
    model_name: str | None
    plate_number: str | None
    conversation_excerpt_url: str | None


class WorkshopQuoteEnvelope(CamelModel):
    data: WorkshopQuoteOut


class DateRange(CamelModel):
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None
