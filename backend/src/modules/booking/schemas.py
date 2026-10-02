"""Booking module — request/response schemas (camelCase JSON, ``{"data": ...}`` envelope).

Shapes follow ``docs/specs/sprint-3/api/us-029-sprint-3-spec.api.md``.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.common.money import Money


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, protected_namespaces=())


# ── API-BK-01 nearby ───────────────────────────────────────────────────────
class OperatingHoursOut(CamelModel):
    is_closed: bool
    open_time: time | None = None
    close_time: time | None = None


class SlotAvailabilityOut(CamelModel):
    date: date
    time_slot: time
    available: bool
    remaining: int
    confirmation_token: str | None = None


class NearbyWorkshopOut(CamelModel):
    workshop_id: UUID
    name: str
    address: str
    region: str
    distance_km: float | None = None
    is_preferred: bool = False
    operating_hours_today: OperatingHoursOut | None = None
    availability: SlotAvailabilityOut | None = None


class AnchorOut(CamelModel):
    source: str
    province: str | None = None
    lat: float | None = None
    lng: float | None = None
    query: str | None = None
    ranked_by: str


class NearbyData(CamelModel):
    anchor: AnchorOut
    workshops: list[NearbyWorkshopOut]


class NearbyEnvelope(CamelModel):
    data: NearbyData


# ── API-BK-02 availability ───────────────────────────────────────────────────
class SlotOut(CamelModel):
    time_slot: time
    available: bool
    remaining: int


class RequestedSlotOut(CamelModel):
    time_slot: time
    available: bool
    remaining: int
    confirmation_token: str | None = None


class AlternativeOut(CamelModel):
    workshop_id: UUID
    name: str
    date: date
    time_slot: time
    remaining: int


class AvailabilityData(CamelModel):
    workshop_id: UUID
    date: date
    requested: RequestedSlotOut | None = None
    slots: list[SlotOut]
    alternatives: list[AlternativeOut]


class AvailabilityEnvelope(CamelModel):
    data: AvailabilityData


# ── API-BK-03 create (owner Confirm → hold [+auto confirm]) ──────────────────
class HoldRequest(CamelModel):
    confirmation_token: str = Field(..., min_length=1)
    user_vehicle_id: UUID
    quote_id: str | None = None
    milestone_ref: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class BookingOut(CamelModel):
    booking_id: UUID
    status: str
    confirmation_mode: str
    workshop_id: UUID
    workshop_name: str | None = None
    booking_date: date
    time_slot: time
    hold_expires_at: datetime | None = None
    owner_cancelable_until: datetime | None = None
    booking_code: str | None = None
    qr_url: str | None = None
    estimated_cost: Decimal | None = None
    estimate_label: str = "Chi phí ước tính"
    quote_id: str | None = None


class BookingEnvelope(CamelModel):
    data: BookingOut


# ── API-BK-04 cancel hold ────────────────────────────────────────────────────
class CancelData(CamelModel):
    booking_id: UUID
    status: str


class CancelEnvelope(CamelModel):
    data: CancelData


# ── us-033 / us-053 — booking ticket (API-BR-01, API-BT-01..04) ──────────────
class TicketWorkshopOut(CamelModel):
    workshop_id: UUID
    name: str
    address: str | None = None
    phone: str | None = None


class TicketVehicleOut(CamelModel):
    user_vehicle_id: UUID
    model_name: str | None = None
    plate_masked: str | None = None


class TicketItemOut(CamelModel):
    item_name: str
    covered: bool


class TicketCostOut(CamelModel):
    amount: Money | None = None
    label: str  # APPROVED_QUOTE / ESTIMATE / NONE
    quote_id: UUID | None = None


class TicketHistoryOut(CamelModel):
    type: str  # STATUS / RESCHEDULE
    at: datetime
    actor_type: str
    source: str
    from_status: str | None = None
    to_status: str | None = None
    reason_code: str | None = None
    from_date: date | None = None
    from_time_slot: time | None = None
    to_date: date | None = None
    to_time_slot: time | None = None


class TicketOut(CamelModel):
    booking_id: UUID
    booking_code: str | None
    status: str
    booking_date: date
    time_slot: time
    appointment_at: datetime
    workshop: TicketWorkshopOut
    vehicle: TicketVehicleOut
    estimated_cost: Money | None = None
    estimate_label: str = "Chi phí ước tính"
    qr_url: str | None = None
    qr_payload: str | None = None
    attendance_confirmed_at: datetime | None = None
    allowed_actions: list[str]
    reschedule_mode: str
    reschedule_blocked_reason: str | None = None
    odo_milestone: int | None = None
    items: list[TicketItemOut] = []
    cost: TicketCostOut
    documents_to_bring: list[str] = []
    reschedule_count: int = 0
    reschedule_deadline: datetime | None = None
    history: list[TicketHistoryOut] = []


class TicketEnvelope(CamelModel):
    data: TicketOut


class MyBookingItemOut(CamelModel):
    booking_id: UUID
    booking_code: str | None
    status: str
    appointment_at: datetime
    booking_date: date
    time_slot: time
    workshop: TicketWorkshopOut
    cost: TicketCostOut
    allowed_actions: list[str]


class MyBookingsData(CamelModel):
    items: list[MyBookingItemOut]
    next_cursor: str | None = None


class MyBookingsEnvelope(CamelModel):
    data: MyBookingsData


class AttendanceData(CamelModel):
    booking_id: UUID
    status: str
    attendance_confirmed_at: datetime


class AttendanceEnvelope(CamelModel):
    data: AttendanceData


class OwnerCancelSource(StrEnum):
    REMINDER_24H = "REMINDER_24H"
    APP = "APP"


class OwnerCancelRequest(CamelModel):
    source: OwnerCancelSource
    reason: str | None = Field(default=None, max_length=255)


class OwnerCancelData(CamelModel):
    booking_id: UUID
    status: str
    cancelled_at: datetime
    cancelled_by: str
    source: str


class OwnerCancelEnvelope(CamelModel):
    data: OwnerCancelData


class BookingByCodeData(CamelModel):
    booking_id: UUID


class BookingByCodeEnvelope(CamelModel):
    data: BookingByCodeData


class RescheduleSource(StrEnum):
    APP = "APP"
    REMINDER_24H = "REMINDER_24H"


class RescheduleRequest(CamelModel):
    confirmation_token: str = Field(..., min_length=1)
    source: RescheduleSource = RescheduleSource.APP
