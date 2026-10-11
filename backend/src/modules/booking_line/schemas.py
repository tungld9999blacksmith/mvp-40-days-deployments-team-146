"""Two-tier booking pricing — request/response schemas (camelCase JSON, ``{"data": ...}`` envelope)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from src.common.money import Money

from .domain import MAX_PHOTOS, REASON_MAX

_PRICE = {"ge": 0, "le": 999_999_999.99, "decimal_places": 2}


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ── responses ───────────────────────────────────────────────────────────────
class LinePhotoOut(CamelModel):
    photo_id: UUID
    url: str | None  # signed, short-lived; None when the storage is unreachable


class LineOut(CamelModel):
    line_id: UUID
    kind: str  # PACKAGE | EXTRA
    status: str  # PENDING_CONFIRM | CONFIRMED | PROPOSED | APPROVED | DECLINED | WITHDRAWN
    item_code: str | None
    item_name: str
    # Price shown at booking time (package) or proposed by the workshop (extra).
    unit_price: Money
    # Price the workshop confirmed after check-in (package lines only).
    confirmed_price: Money | None
    # What the line costs once settled.
    price: Money
    price_source: str | None
    # "Giá xưởng" | "Giá tham khảo" | "Xưởng đã xác nhận" | "Bảo hành" | "Phát sinh"
    price_label: str
    is_covered_by_warranty: bool
    is_safety_critical: bool
    reason: str | None
    version: int
    confirmed_at: datetime | None = None
    decided_at: datetime | None = None
    # APP | PHONE (the workshop recorded the owner's answer by phone) | None while undecided.
    decided_via: str | None = None
    phone_confirmed_by: str | None = None
    # Set when the owner disputed a phone decision; the line went back to PROPOSED.
    disputed_at: datetime | None = None
    # A phone decision the owner can still dispute (booking not completed yet).
    can_dispute: bool = False
    # PROPOSED lines: the owner is asked to answer by then; after it the workshop calls them.
    reply_due_at: datetime | None = None
    # The deadline has passed while the car is still at the workshop: call the owner.
    call_owner: bool = False
    created_at: datetime
    photos: list[LinePhotoOut] = []


class PricingFlowOut(CamelModel):
    """Flow of NEW bookings (QUOTE_FLOW); each booking keeps its own ``pricingFlow``."""

    quote_flow: str  # legacy | two_tier


class PricingFlowEnvelope(CamelModel):
    data: PricingFlowOut


class BlockedActionOut(CamelModel):
    action: str  # START | COMPLETE
    reason_code: str
    message: str


class LinesOut(CamelModel):
    booking_id: UUID
    booking_status: str
    pricing_flow: str  # legacy | two_tier
    # Shown when a two-tier booking has no package lines (no rule for the milestone, D9).
    package_notice: str | None = None
    lines: list[LineOut]
    # Σ CONFIRMED + APPROVED — what the owner pays now.
    current_total: Money
    # current_total + every line still waiting for a decision or a confirmation.
    total_if_all_approved: Money
    pending_decision_count: int
    unconfirmed_count: int
    blocked_actions: list[BlockedActionOut] = []


class LinesEnvelope(CamelModel):
    data: LinesOut


# ── requests ────────────────────────────────────────────────────────────────
class ConfirmPackageRequest(CamelModel):
    expected_version: int = Field(ge=1)
    price: Money = Field(**_PRICE)
    # Required (10-500) only when the price is above the reference price.
    reason: str | None = Field(default=None, max_length=REASON_MAX)


class ProposeExtraRequest(CamelModel):
    # Catalog item of the vehicle's model, or None for a free-text item.
    item_code: str | None = Field(default=None, max_length=50)
    item_name: str | None = Field(default=None, max_length=200)
    price: Money = Field(**_PRICE)
    reason: str = Field(max_length=REASON_MAX)
    is_safety_critical: bool = False
    photo_keys: list[str] = Field(default_factory=list, max_length=MAX_PHOTOS)


class EditLineRequest(CamelModel):
    expected_version: int = Field(ge=1)
    price: Money = Field(**_PRICE)
    reason: str | None = Field(default=None, max_length=REASON_MAX)
    item_name: str | None = Field(default=None, max_length=200)
    is_safety_critical: bool | None = None


class WithdrawRequest(CamelModel):
    expected_version: int = Field(ge=1)


class Decision(StrEnum):
    APPROVE = "APPROVE"
    DECLINE = "DECLINE"


class DecideRequest(CamelModel):
    decision: Decision
    # The version the owner saw; a newer version means the workshop changed the line.
    seen_version: int = Field(ge=1)
    # Declining a safety item needs this second confirmation.
    confirm_safety: bool = False


class PhoneDecisionRequest(CamelModel):
    """The owner answered by phone; the workshop records it (the owner can dispute it until COMPLETE)."""

    decision: Decision
    seen_version: int = Field(ge=1)
    # Who answered the phone, e.g. "Anh Trung (chủ xe)".
    confirmed_by_name: str = Field(max_length=100)
    confirm_safety: bool = False

    @field_validator("confirmed_by_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Enter who confirmed by phone.")
        return value


class DisputeRequest(CamelModel):
    # The version the owner saw on the ticket.
    seen_version: int = Field(ge=1)


class PhotoUploadRequest(CamelModel):
    content_type: str


class PhotoUploadOut(CamelModel):
    key: str
    upload_url: str
    token: str | None = None


class PhotoUploadEnvelope(CamelModel):
    data: PhotoUploadOut
