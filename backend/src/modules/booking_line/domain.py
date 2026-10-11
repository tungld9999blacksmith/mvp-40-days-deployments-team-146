"""Two-tier booking pricing — pure rules (docs/designs/bao-gia-hai-tang.md).

No DB access: the service, the booking state machine and the tests share these.

Line state machine::

    PACKAGE workshop price / warranty ───────────────────────────► CONFIRMED
    PACKAGE reference price ─► PENDING_CONFIRM ─┬─ ≤ reference ──► CONFIRMED (owner told)
                                                └─ > reference ─► PROPOSED ─┬─► APPROVED
                                                                            └─► DECLINED (not done)
    EXTRA ─► PROPOSED ─┬─► APPROVED   (owner, WHERE status='PROPOSED' AND version=:seen)
                       ├─► DECLINED   (safety item → one more confirmation)
                       └─► WITHDRAWN  (workshop, only while PROPOSED)

    PROPOSED ─► APPROVED / DECLINED by phone (workshop records it, decided_via=PHONE)
             ◄─ "Tôi không đồng ý" (owner, until COMPLETE): back to PROPOSED

Booking guards (BookingStateMachine): START needs no ``PENDING_CONFIRM`` line (D8);
COMPLETE needs no ``PENDING_CONFIRM`` / ``PROPOSED`` line and sets
``actual_cost`` = Σ CONFIRMED + APPROVED (D6).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.common.core.maintenance.booking import BookingStatus
from src.common.core.maintenance.booking_line import BookingLine, LineKind, LineStatus
from src.common.core.maintenance.service_progress import ServiceStage

REASON_MIN = 10
REASON_MAX = 500
MAX_PHOTOS = 3
MAX_PHOTO_BYTES = 5 * 1024 * 1024
PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

# Extras are proposed while the car is being inspected or serviced; never from QUALITY_CHECK on.
EXTRA_STAGES: frozenset[ServiceStage] = frozenset(
    {ServiceStage.INSPECTING, ServiceStage.SERVICING, ServiceStage.WAITING_PARTS}
)

BILLABLE: frozenset[LineStatus] = frozenset({LineStatus.CONFIRMED, LineStatus.APPROVED})
UNSETTLED: frozenset[LineStatus] = frozenset({LineStatus.PENDING_CONFIRM, LineStatus.PROPOSED})

# The owner decides (or disputes a phone decision) only while the car is at the workshop.
DECIDABLE_STATUSES = (BookingStatus.CHECKED_IN, BookingStatus.IN_PROGRESS)
DECIDED_VIA_APP = "APP"
DECIDED_VIA_PHONE = "PHONE"

# Open question 2 of the design (decided 2026-10-11): a line waiting for the owner gets
# an answer within 10 minutes, or the workshop calls. Both sides see the deadline.
OWNER_REPLY_SLA = timedelta(minutes=10)

PACKAGE_NO_RULE_NOTICE = "Giá gói do xưởng báo khi nhận xe"
REFERENCE_NOTICE = "Giá tham khảo, xưởng xác nhận khi nhận xe"
DECLINED_HISTORY_NOTE = "Chủ xe từ chối hạng mục"


def reply_due_at(line: BookingLine) -> datetime | None:
    """When the workshop should call the owner about a line still waiting for them."""
    asked = line.asked_at
    if line.line_status != LineStatus.PROPOSED or asked is None:
        return None
    if asked.tzinfo is None:  # SQLite drops tzinfo
        asked = asked.replace(tzinfo=UTC)
    return asked + OWNER_REPLY_SLA


def reason_valid(reason: str | None) -> bool:
    return REASON_MIN <= len((reason or "").strip()) <= REASON_MAX


def billable_total(lines: Iterable[BookingLine]) -> Decimal:
    """``actual_cost`` of a two-tier booking: Σ price of CONFIRMED + APPROVED lines."""
    return sum((line.price for line in lines if line.line_status in BILLABLE), Decimal(0)).quantize(Decimal("0.01"))


def total_if_all_approved(lines: Iterable[BookingLine]) -> Decimal:
    """What the owner pays if every line still waiting is approved."""
    return sum(
        (line.price for line in lines if line.line_status in BILLABLE or line.line_status in UNSETTLED),
        Decimal(0),
    ).quantize(Decimal("0.01"))


def start_block(lines: Iterable[BookingLine]) -> int:
    """Number of package lines whose reference price is not confirmed yet (blocks START)."""
    return sum(1 for line in lines if line.line_status == LineStatus.PENDING_CONFIRM)


def complete_block(lines: Iterable[BookingLine]) -> int:
    """Number of lines that still need the workshop or the owner (blocks COMPLETE)."""
    return sum(1 for line in lines if line.line_status in UNSETTLED)


def declined_package(lines: Iterable[BookingLine]) -> list[BookingLine]:
    """Standard items the owner refused (D10): not done, not charged, kept in history."""
    return [line for line in lines if line.kind == LineKind.PACKAGE and line.line_status == LineStatus.DECLINED]


def package_status(price_source: str | None, covered: bool) -> LineStatus:
    """Initial status of a package line snapshotted from the estimate."""
    if covered or price_source != "REFERENCE_PRICE":
        return LineStatus.CONFIRMED
    return LineStatus.PENDING_CONFIRM
