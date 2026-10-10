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

Booking guards (BookingStateMachine): START needs no ``PENDING_CONFIRM`` line (D8);
COMPLETE needs no ``PENDING_CONFIRM`` / ``PROPOSED`` line and sets
``actual_cost`` = Σ CONFIRMED + APPROVED (D6).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from decimal import Decimal

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

PACKAGE_NO_RULE_NOTICE = "Giá gói do xưởng báo khi nhận xe"
REFERENCE_NOTICE = "Giá tham khảo, xưởng xác nhận khi nhận xe"
DECLINED_HISTORY_NOTE = "Chủ xe từ chối hạng mục"

# Open question 3 of the design: until the manufacturer list exists, an item is
# safety-critical when its name mentions brakes, tyres, steering or lights.
_SAFETY_WORDS = ("phanh", "lop", "vo xe", "lai", "vo lang", "den", "brake", "tire", "tyre", "steering", "light")


def _fold(text: str) -> str:
    """Lower-case and strip Vietnamese diacritics (``Đèn`` → ``den``)."""
    text = text.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def is_safety_item(item_name: str) -> bool:
    words = f" {' '.join(_fold(item_name).split())} "
    return any(f" {w} " in words for w in _SAFETY_WORDS)


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
