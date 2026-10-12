from __future__ import annotations

from typing import Any

from src.infrastructure.prompts import load_prompt
from src.modules.booking.domain import now_vn

EV_CARE_BASE_PROMPT = load_prompt("ev_care_base")

_WEEKDAYS_VI = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


def _today_line() -> str:
    today = now_vn().date()
    return f"Hôm nay: {_WEEKDAYS_VI[today.weekday()]}, {today.isoformat()} (giờ Việt Nam)"


def format_system_prompt(vehicle_context: dict[str, Any] | None = None) -> str:
    """Format system prompt kèm theo ngữ cảnh xe được nạp trước."""
    if not vehicle_context:
        context_str = """
[NGỮ CẢNH XE HIỆN TẠI]
Chưa có xe nào được chọn hoặc tài khoản chưa liên kết xe. Nếu người dùng hỏi về xe cụ thể, hãy lịch sự hỏi dòng xe và số ODO hiện tại của họ.
"""
    else:
        model = vehicle_context.get("model") or vehicle_context.get("vehicle_model") or "Không rõ"
        odo = vehicle_context.get("current_odo") or vehicle_context.get("current_odometer_km") or 0
        last_service_odo = vehicle_context.get("last_service_odo") or vehicle_context.get("last_service_odometer_km")
        months_since_last = vehicle_context.get("months_since_last") or vehicle_context.get("months_since_last_service")
        plate = vehicle_context.get("license_plate") or vehicle_context.get("plate_number", "")
        vehicle_id = vehicle_context.get("id") or vehicle_context.get("vehicle_id", "")

        # Phiên chat chưa nạp ODO (0 / trống): số thật nằm trong kết quả get_due_maintenance.
        odo_km = int(odo) if isinstance(odo, (int, float)) or (isinstance(odo, str) and odo.isdigit()) else 0
        odo_str = f"{odo_km:,} km" if odo_km > 0 else "Xem get_due_maintenance"
        if last_service_odo is not None and (
            isinstance(last_service_odo, (int, float))
            or (isinstance(last_service_odo, str) and last_service_odo.isdigit())
        ):
            last_service_str = f"{int(last_service_odo):,} km (cách đây {months_since_last or 0} tháng)"
        elif last_service_odo:
            last_service_str = f"{last_service_odo} km (cách đây {months_since_last or 0} tháng)"
        else:
            last_service_str = "Xem get_due_maintenance"

        context_str = f"""
[NGỮ CẢNH XE HIỆN TẠI (ĐÃ NẠP SẴN TỪ PHIÊN LÀM VIỆC)]
- Dòng xe: {model}
- Biển số: {plate or "Chưa cập nhật"}
- ODO hiện tại: {odo_str}
- Lần bảo dưỡng gần nhất: {last_service_str}
- Vehicle ID: {vehicle_id or "Chưa cập nhật"}
"""

    return f"{EV_CARE_BASE_PROMPT}\n{context_str}{_today_line()}\n"

