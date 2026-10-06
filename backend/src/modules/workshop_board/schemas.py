"""Workshop Board — request/response schemas (us-037 §3-§9)."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.common.money import Money


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BookingStatusIn(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# ── API-WB-01 / 02 / 03 ─────────────────────────────────────────────────────
class CustomerOut(CamelModel):
    full_name: str | None
    phone: str | None = None


class VehicleOut(CamelModel):
    model_name: str | None
    license_plate: str | None


class BoardItemOut(CamelModel):
    booking_id: UUID
    booking_code: str
    status: str
    booking_date: date
    time_slot: time
    customer: CustomerOut
    vehicle: VehicleOut
    milestone_label: str | None = None
    estimated_cost: Money | None = None
    attendance_confirmed_at: datetime | None = None
    confirm_deadline: datetime | None = None
    allowed_actions: list[str]


class BoardListData(CamelModel):
    workshop_id: UUID
    confirmation_mode: str
    from_: date = Field(alias="from")
    to: date
    summary: dict[str, int]
    items: list[BoardItemOut]


class BoardListEnvelope(CamelModel):
    data: BoardListData


class StatusEventOut(CamelModel):
    from_status: str | None
    to_status: str
    actor_type: str
    source: str
    reason_code: str | None
    note: str | None
    at: datetime


class BoardDetailOut(BoardItemOut):
    actual_cost: Money | None = None
    note: str | None = None
    status_history: list[StatusEventOut]


class BoardDetailEnvelope(CamelModel):
    data: BoardDetailOut


class ByCodeOut(BoardItemOut):
    check_in_eligibility: str
    checked_in_at: datetime | None = None


class ByCodeEnvelope(CamelModel):
    data: ByCodeOut


# ── API-WB-04 ───────────────────────────────────────────────────────────────
class BoardAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    CHECK_IN = "CHECK_IN"
    START = "START"
    COMPLETE = "COMPLETE"
    CANCEL = "CANCEL"


class TransitionSource(StrEnum):
    BOARD = "BOARD"
    QR_SCAN = "QR_SCAN"


class TransitionRequest(CamelModel):
    action: BoardAction
    expected_status: BookingStatusIn
    reason_code: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=255)
    actual_cost: Money | None = Field(default=None, ge=0, le=999_999_999.99, decimal_places=2)
    source: TransitionSource = TransitionSource.BOARD


class TransitionEffectsOut(CamelModel):
    service_record_id: UUID | None = None
    follow_up_id: UUID | None = None
    follow_up_scheduled_at: datetime | None = None
    reminder_scheduled: bool | None = None


class TransitionOut(CamelModel):
    booking_id: UUID
    status: str
    actual_cost: Money | None = None
    effects: TransitionEffectsOut | None = None
    allowed_actions: list[str]


class TransitionEnvelope(CamelModel):
    data: TransitionOut


# ── API-WB-05 / 06 ──────────────────────────────────────────────────────────
class CapacitySlotOut(CamelModel):
    time_slot: time
    occupied: int
    blocked: int
    remaining: int
    max_block: int
    block_reason: str | None = None
    block_note: str | None = None


class CapacityDayOut(CamelModel):
    date: date
    is_closed: bool
    open_time: time | None = None
    close_time: time | None = None
    slots: list[CapacitySlotOut]


class CapacityData(CamelModel):
    total_technicians: int
    emergency_slots_reserved: int
    days: list[CapacityDayOut]


class CapacityEnvelope(CamelModel):
    data: CapacityData


class BlockReasonIn(StrEnum):
    PHONE_BOOKING = "PHONE_BOOKING"
    WALK_IN = "WALK_IN"
    MAINTENANCE = "MAINTENANCE"
    OTHER = "OTHER"


class SlotBlockRequest(CamelModel):
    date: date
    time_slot: time
    blocked_count: int = Field(..., ge=0)
    reason: BlockReasonIn | None = None
    note: str | None = Field(default=None, max_length=255)


class SlotBlockOut(CamelModel):
    date: date
    time_slot: time
    blocked: int
    occupied: int
    remaining: int
    max_block: int


class SlotBlockEnvelope(CamelModel):
    data: SlotBlockOut


# ── API-WB-07 / 08 ──────────────────────────────────────────────────────────
class ConfirmationModeIn(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class BookingSettingsRequest(CamelModel):
    confirmation_mode: ConfirmationModeIn


class BookingSettingsOut(CamelModel):
    confirmation_mode: str
    ws_confirm_deadline_hours: int
    pending_count: int


class BookingSettingsEnvelope(CamelModel):
    data: BookingSettingsOut
