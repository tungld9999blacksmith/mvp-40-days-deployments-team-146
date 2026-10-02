"""Follow-up & support tickets — request/response schemas (us-041 §3-§7)."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.common.money import Money


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ── owner: follow-up (API-FU-01/02) ─────────────────────────────────────────
class FollowUpBookingOut(CamelModel):
    booking_id: UUID
    booking_code: str
    booking_date: date


class WorkshopContactOut(CamelModel):
    name: str
    hotline: str | None = None


class ResponseOut(CamelModel):
    rating: int
    comment: str | None
    responded_at: datetime


class TicketRefOut(CamelModel):
    ticket_id: UUID
    status: str


class OutcomeOut(CamelModel):
    has_issue: bool
    safety_advice: bool
    message: str | None = None
    safety_message: str | None = None
    ticket: TicketRefOut | None = None


class FollowUpOut(CamelModel):
    follow_up_id: UUID
    status: str
    closed_reason: str | None = None
    can_respond: bool
    respond_before: datetime | None = None
    question: str
    booking: FollowUpBookingOut
    workshop: WorkshopContactOut
    response: ResponseOut | None = None
    outcome: OutcomeOut | None = None


class FollowUpEnvelope(CamelModel):
    data: FollowUpOut


class RespondRequest(CamelModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class RespondOut(CamelModel):
    follow_up_id: UUID
    status: str
    outcome: OutcomeOut


class RespondEnvelope(CamelModel):
    data: RespondOut


# ── owner: support tickets (API-FU-03/04) ───────────────────────────────────
class OwnerTicketItemOut(CamelModel):
    ticket_id: UUID
    status: str
    issue_summary: str
    workshop_name: str | None
    booking_date: date | None
    created_at: datetime
    updated_at: datetime


class OwnerTicketListData(CamelModel):
    items: list[OwnerTicketItemOut]
    next_cursor: str | None = None


class OwnerTicketListEnvelope(CamelModel):
    data: OwnerTicketListData


class FeedbackOut(CamelModel):
    rating: int | None
    comment: str | None


class OwnerTicketOut(CamelModel):
    ticket_id: UUID
    status: str
    issue_summary: str
    your_feedback: FeedbackOut
    booking: FollowUpBookingOut
    workshop: WorkshopContactOut
    started_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None


class OwnerTicketEnvelope(CamelModel):
    data: OwnerTicketOut


# ── workshop owner: support tickets (API-FU-05..07) ─────────────────────────
class CustomerOut(CamelModel):
    full_name: str | None
    phone: str | None = None


class VehicleOut(CamelModel):
    model_name: str | None
    license_plate: str | None


class WorkshopTicketItemOut(CamelModel):
    ticket_id: UUID
    status: str
    priority: str
    issue_summary: str
    rating: int | None
    customer: CustomerOut
    vehicle: VehicleOut
    booking_code: str | None
    created_at: datetime


class WorkshopTicketListData(CamelModel):
    summary: dict[str, int]
    items: list[WorkshopTicketItemOut]
    next_cursor: str | None = None


class WorkshopTicketListEnvelope(CamelModel):
    data: WorkshopTicketListData


class WorkshopFeedbackOut(CamelModel):
    rating: int | None
    comment: str | None
    responded_at: datetime | None


class ClassificationOut(CamelModel):
    intent: str | None
    confidence: float | None
    classified_by: str | None


class WorkshopTicketBookingOut(CamelModel):
    booking_id: UUID
    booking_date: date
    time_slot: time
    actual_cost: Money | None


class WorkshopTicketOut(WorkshopTicketItemOut):
    feedback: WorkshopFeedbackOut
    classification: ClassificationOut
    booking: WorkshopTicketBookingOut
    started_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None
    allowed_actions: list[str]


class WorkshopTicketEnvelope(CamelModel):
    data: WorkshopTicketOut


class TicketAction(StrEnum):
    START = "START"
    RESOLVE = "RESOLVE"


class TicketPriorityIn(StrEnum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"


class TicketStatusIn(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class TicketTransitionRequest(CamelModel):
    action: TicketAction
    expected_status: TicketStatusIn
    resolution_note: str | None = Field(default=None, max_length=1000)


class TicketTransitionOut(CamelModel):
    ticket_id: UUID
    status: str
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    allowed_actions: list[str]


class TicketTransitionEnvelope(CamelModel):
    data: TicketTransitionOut
