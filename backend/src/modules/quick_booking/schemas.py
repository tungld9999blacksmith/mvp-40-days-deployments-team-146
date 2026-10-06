"""Quick booking — request/response schemas (us-061 API §4–7).

Same style as the conversation API (camelCase field names, ``data`` envelope).
"""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, Field

from src.infrastructure.messaging import MessageDto


class DeviceLocation(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class QuickBookingRequest(BaseModel):
    clientMessageId: UUID
    location: DeviceLocation | None = None
    province: str | None = Field(default=None, max_length=100)


class QuickBookingData(BaseModel):
    userMessage: MessageDto
    assistantMessage: MessageDto
    replayed: bool = False


class QuickBookingEnvelope(BaseModel):
    data: QuickBookingData


class ProposalBookingOut(BaseModel):
    bookingId: UUID
    bookingCode: str | None = None
    status: str
    confirmationMode: str | None = None
    workshopName: str | None = None
    bookingDate: date
    timeSlot: time
    ownerCancelableUntil: str | None = None


class ConfirmData(BaseModel):
    proposalId: UUID
    status: str
    booking: ProposalBookingOut
    message: MessageDto | None = None
    replayed: bool = False


class ConfirmEnvelope(BaseModel):
    data: ConfirmData


class ReviseRequest(BaseModel):
    workshopId: UUID
    date: date
    timeSlot: time


class ReviseData(BaseModel):
    proposalId: UUID
    message: MessageDto


class ReviseEnvelope(BaseModel):
    data: ReviseData


class CancelData(BaseModel):
    proposalId: UUID
    status: str


class CancelEnvelope(BaseModel):
    data: CancelData
