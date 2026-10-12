"""Notification module - reminder rules as pure functions (FEAT-NOTI-001 BR-501, BR-509).

No FastAPI, no Session: the service loads the inputs and calls these functions.
"""

from __future__ import annotations

from src.common.core.maintenance.reminder import ReminderChannel, ReminderLevel
from src.modules.user_vehicle.domain import DueResult, DueStatus
from src.modules.vehicle_usage.schemas import MaintenanceForecast

from .channels import NotificationMessage

# External channels, in the order used everywhere the channel list is shown.
# Reminders are always shown in the in-app feed, whatever is enabled here.
ALL_CHANNELS: tuple[ReminderChannel, ...] = (
    ReminderChannel.ZALO,
    ReminderChannel.TELEGRAM,
    ReminderChannel.SMS,
    ReminderChannel.EMAIL,
)
DEFAULT_CHANNELS: frozenset[ReminderChannel] = frozenset()

MIN_LEAD_DAYS = 0
MAX_LEAD_DAYS = 30


def decide_level(result: DueResult, *, lead_days: int, due_soon_km: int) -> ReminderLevel | None:
    """BR-501: which reminder level (if any) the vehicle has reached."""
    milestone = result.next_milestone
    if result.due_status is DueStatus.UNKNOWN or milestone is None:
        return None
    if result.due_status is DueStatus.OVERDUE:
        return ReminderLevel.EXPIRED
    if result.remaining_days is not None and result.remaining_days <= lead_days:
        return ReminderLevel.EARLY
    if result.remaining_km is not None and result.remaining_km <= due_soon_km:
        return ReminderLevel.EARLY
    return None


def mask_plate(plate: str) -> str:
    """Keep the first and last two characters (``30A12345`` -> ``30****45``)."""
    if len(plate) <= 4:
        return plate
    return plate[:2] + "*" * (len(plate) - 4) + plate[-2:]


def _km(value: int) -> str:
    """Vietnamese grouping, as in the app: ``12000`` -> ``12.000 km``."""
    return f"{value:,} km".replace(",", ".")


def build_message(
    *,
    model_name: str,
    license_plate: str,
    result: DueResult,
    level: ReminderLevel,
    app_url: str = "",
    forecast: MaintenanceForecast | None = None,
    trip: dict | None = None,
) -> NotificationMessage:
    """BR-509: no VIN / phone / email / national id; plate partly masked; link to the app."""
    milestone = result.next_milestone
    vehicle = f"{model_name} ({mask_plate(license_plate)})"
    # The API label ("12,000 km / 12 months") stays English; messages use their own.
    label = f"{_km(milestone.odo_milestone_km)} / {milestone.month_milestone} tháng"
    due = milestone.due_date.strftime("%d/%m/%Y")
    days = result.remaining_days or 0
    km = result.remaining_km

    if level is ReminderLevel.EXPIRED:
        overdue: list[str] = []
        if days < 0:
            overdue.append(f"{-days} ngày")
        if km is not None and km < 0:
            overdue.append(_km(-km))
        how_late = f"đã quá {' và '.join(overdue)}" if overdue else "vừa quá hạn"
        subject = "Xe đã quá hạn bảo dưỡng"
        body = f"Xe {vehicle} đã quá hạn bảo dưỡng mốc {label} (hạn {due}, {how_late})."
    else:
        # Due at whichever comes first: the date or the km milestone.
        left: list[str] = []
        if days > 0:
            left.append(f"{days} ngày")
        if km is not None and km >= 0:
            left.append(_km(km))
        if days == 0:
            remaining = "đến hạn hôm nay"
        else:
            remaining = f"còn {' hoặc '.join(left)}" if left else "sắp đến hạn"
        subject = "Xe sắp đến hạn bảo dưỡng"
        body = f"Xe {vehicle} sắp đến mốc bảo dưỡng {label} (hạn {due}, {remaining})."

    if forecast and forecast.status == "AVAILABLE" and forecast.km_forecast_date:
        body += f" Mức sử dụng khoảng {forecast.avg_km_per_day:g} km/ngày; dự kiến chạm mốc km {forecast.km_forecast_date.strftime('%d/%m/%Y')} nếu duy trì mức sử dụng này."
    if trip:
        body += f" Chuyến đi khai báo ngày {trip['departureDate']}, khoảng {trip['distanceKm']} km: nên lên kế hoạch bảo dưỡng trước khi đi. Quãng đường này chưa phải ODO đã ghi nhận."
    link = f"{app_url.rstrip('/')}/booking" if app_url else None
    if link:
        body += f" Đặt lịch bảo dưỡng: {link}"
    return NotificationMessage(subject=subject, body=body, link=link)
