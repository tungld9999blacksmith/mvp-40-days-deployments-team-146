"""Vietnamese templates v1. Numeric facts are provided by the due-status service."""

from html import escape
from urllib.parse import urlencode, urlparse

from src.common.core.maintenance.reminder import ReminderLevel
from src.modules.user_vehicle.domain import DueResult

from .channels import NotificationMessage
from .domain import mask_plate


def snapshot(result: DueResult, *, lead_days: int, due_soon_km: int) -> dict:
    milestone = result.next_milestone
    if milestone is None:
        raise ValueError("Cannot render an unknown milestone")
    km_hit = result.remaining_km is not None and result.remaining_km <= due_soon_km
    time_hit = result.remaining_days is not None and result.remaining_days <= lead_days
    if result.due_status.value == "OVERDUE":
        km_hit = result.remaining_km is not None and result.remaining_km < 0
        time_hit = result.remaining_days is not None and result.remaining_days < 0
    return {
        "templateVersion": "maintenance-v1",
        "dueStatus": result.due_status.value,
        "reason": "BOTH" if km_hit and time_hit else "KM" if km_hit else "TIME",
        "dueDate": milestone.due_date.isoformat(),
        "remainingKm": result.remaining_km,
        "remainingDays": result.remaining_days,
        "monthMilestone": milestone.month_milestone,
        "odometerKm": result.odometer.odo_km if result.odometer else None,
        "odometerRecordedAt": result.odometer.recorded_at.isoformat() if result.odometer else None,
        "odometerStale": result.odometer.is_stale if result.odometer else False,
        "leadDays": lead_days,
        "dueSoonKm": due_soon_km,
        "items": [{"itemCode": i.item_code, "itemName": i.item_name} for i in milestone.items],
    }


def build_email_message(
    *,
    model_name: str,
    license_plate: str,
    milestone_km: int,
    level: ReminderLevel,
    details: dict,
    app_url: str,
    reminder_id: str,
    delivery_id: str,
    recipient_hash: str,
    sender: str,
) -> NotificationMessage:
    base = app_url.rstrip("/")
    if urlparse(base).scheme not in ("http", "https") or not urlparse(base).netloc:
        raise ValueError("A public app URL is required for email links")
    reason = {"KM": "theo số km", "TIME": "theo thời gian", "BOTH": "theo số km và thời gian"}[details["reason"]]
    state = "đã quá hạn" if level is ReminderLevel.EXPIRED else "sắp đến mốc"
    subject = f"[EV Care] Xe của bạn {state} bảo dưỡng"
    lines = [
        f"Xe {model_name} ({mask_plate(license_plate)}) {state} bảo dưỡng.",
        f"Mốc: {milestone_km:,} km / {details['monthMilestone']} tháng.",
        f"Hạn theo thời gian: {details['dueDate']}.",
        f"Lý do nhắc: {reason}.",
    ]
    if details["odometerKm"] is not None:
        lines.append(f"ODO ghi nhận: {details['odometerKm']:,} km; cập nhật: {details['odometerRecordedAt']}.")
        if details["odometerStale"]:
            lines.append("Dữ liệu ODO đã cũ; số km còn lại được tính từ lần ghi nhận này.")
    else:
        lines.append("Chưa có ODO; lời nhắc chỉ dựa theo thời gian.")
    if details["remainingKm"] is not None:
        km = details["remainingKm"]
        lines.append(f"{'Còn' if km >= 0 else 'Quá mốc'} {abs(km):,} km.")
    if details["remainingDays"] is not None:
        days = details["remainingDays"]
        lines.append(f"{'Còn' if days >= 0 else 'Quá hạn'} {abs(days)} ngày.")
    if details.get("items"):
        lines.append("Hạng mục: " + "; ".join(i["itemName"] for i in details["items"]) + ".")
    query = urlencode({"action": "booking"})
    link = f"{base}/notifications/reminders/{reminder_id}"
    actions = [
        ("Đặt lịch bảo dưỡng", f"{link}?{query}"),
        ("Hỏi trợ lý", f"{link}?action=chat"),
        ("Cài đặt / tắt nhận email", f"{base}/notifications/settings#channel-EMAIL"),
    ]
    body = "\n".join(lines + [f"{label}: {url}" for label, url in actions])
    paragraphs = "".join(f"<p>{escape(line)}</p>" for line in lines)
    buttons = "".join(
        f'<p><a href="{escape(url, quote=True)}" style="color:#007A52">{escape(label)}</a></p>'
        for label, url in actions
    )
    html = f'<html lang="vi"><body style="font-family:Arial,sans-serif;color:#111820"><h2>EV Care</h2>{paragraphs}{buttons}</body></html>'
    return NotificationMessage(subject, body, link, html, "MAINTENANCE_REMINDER", delivery_id, recipient_hash, sender)
