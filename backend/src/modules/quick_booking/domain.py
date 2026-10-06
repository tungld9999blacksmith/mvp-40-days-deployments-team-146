"""Quick booking — pure rules (us-061 BR-1503, BR-1504).

No DB / Redis here, so the slot window and the texts stay unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from src.modules.booking.domain import TZ_VN

QUICK_BOOKING_LABEL = "Đặt lịch bảo dưỡng nhanh"
CARD_PROPOSAL = "BOOKING_PROPOSAL"
CARD_NEED_LOCATION = "QUICK_BOOKING_NEED_LOCATION"
CARD_VERSION = 1

_WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


@dataclass(frozen=True)
class QuickBookingConfig:
    """Tunables from ``.env`` (see ``config.Settings``, prefix ``QUICK_BOOKING_``)."""

    proposal_ttl_minutes: int = 30  # BR-1508
    min_lead_minutes: int = 120  # BR-1504
    horizon_days: int = 14  # BR-1504
    not_due_lead_days: int = 7  # BR-1504 (NORMAL)
    max_lookahead_days: int = 60  # EF-1504
    max_workshops: int = 5  # BR-1506
    max_alternatives: int = 2  # BR-1507
    ws_confirm_deadline_hours: int = 12  # us-029 BR-015, shown for PENDING results


@dataclass(frozen=True)
class SlotWindow:
    """Slots that start at or after ``earliest`` and on or before ``last_day``."""

    earliest: datetime
    last_day: date
    after_due: bool = False  # DUE_SOON fallback past the due date

    def days(self) -> list[date]:
        first = self.earliest.date()
        return [first + timedelta(days=i) for i in range((self.last_day - first).days + 1)]

    def accepts(self, d: date, t: time) -> bool:
        return d <= self.last_day and datetime.combine(d, t, tzinfo=TZ_VN) >= self.earliest


def slot_windows(due_status: str, due_date: date, now: datetime, config: QuickBookingConfig) -> list[SlotWindow] | None:
    """BR-1504 — windows to scan, in order; ``None`` when a NORMAL vehicle is too far from due (EF-1504)."""
    earliest = now + timedelta(minutes=config.min_lead_minutes)
    horizon_end = now.date() + timedelta(days=config.horizon_days)
    if due_status == "OVERDUE":
        return [SlotWindow(earliest, horizon_end)]
    if due_status == "DUE_SOON":
        windows = []
        if due_date >= earliest.date():
            windows.append(SlotWindow(earliest, min(due_date, horizon_end)))
        if due_date < horizon_end:
            windows.append(SlotWindow(earliest, horizon_end, after_due=True))
        return windows
    # NORMAL: around the due date, never earlier than the lead time.
    start_day = due_date - timedelta(days=config.not_due_lead_days)
    if start_day > now.date() + timedelta(days=config.max_lookahead_days):
        return None
    start = max(earliest, datetime.combine(start_day, time.min, tzinfo=TZ_VN))
    return [SlotWindow(start, due_date)]


def format_day(d: date) -> str:
    return f"{_WEEKDAYS[d.weekday()]}, {d.strftime('%d/%m/%Y')}"


def format_slot(d: date, t: time) -> str:
    return f"{t.strftime('%H:%M')} {format_day(d)}"


def format_km(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " km"


def mask_plate(plate: str | None) -> str | None:
    """Keep the first 3 and last 2 characters (``30A***45``)."""
    if not plate:
        return None
    return plate if len(plate) <= 5 else plate[:3] + "***" + plate[-2:]


def reason_text(
    due_status: str,
    odo_milestone_km: int,
    due_date: date,
    remaining_km: int | None,
    remaining_days: int,
    *,
    after_due: bool = False,
) -> str:
    """BR-1503 — why this milestone and this kind of slot."""
    milestone = format_km(odo_milestone_km)
    if due_status == "OVERDUE":
        parts = []
        if remaining_km is not None and remaining_km < 0:
            parts.append(format_km(-remaining_km))
        if remaining_days < 0:
            parts.append(f"{-remaining_days} ngày")
        late = " / ".join(parts) or "hạn"
        return f"Xe đã quá mốc {milestone}: quá {late}. Đề xuất khung giờ sớm nhất còn trống."
    left = []
    if remaining_km is not None:
        left.append(format_km(max(remaining_km, 0)))
    left.append(f"{max(remaining_days, 0)} ngày")
    gap = " / ".join(left)
    due = due_date.strftime("%d/%m/%Y")
    if due_status == "DUE_SOON":
        tail = (
            "Không còn khung giờ trước hạn nên đề xuất khung sớm nhất sau ngày hạn."
            if after_due
            else "Đề xuất lịch trước hạn."
        )
        return f"Xe còn {gap} tới mốc {milestone} (hạn {due}). {tail}"
    return f"Xe chưa đến hạn: còn {gap} tới mốc {milestone} (hạn {due}). Đề xuất lịch gần hạn."
