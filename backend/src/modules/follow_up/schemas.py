"""Post-service follow-up — request/response schemas (us-041 §3-§4)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


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


class OutcomeOut(CamelModel):
    has_issue: bool
    safety_advice: bool
    message: str | None = None
    safety_message: str | None = None


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
