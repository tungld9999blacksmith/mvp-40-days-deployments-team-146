from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Bảng quy tắc bảo dưỡng tiêu chuẩn VinFast dự phòng khi DB offline
STANDARD_MAINTENANCE_RULES: dict[str, Any] = {
    # Dòng xe máy điện (Evo200, Feliz, Klara, Theon, Vento)
    "escooter": {
        "milestones": [
            {
                "odo": 1000,
                "months": 1,
                "name": "Mốc ban đầu (1.000 km hoặc 1 tháng)",
                "item_codes": ["INITIAL_INSPECTION", "CHASSIS_BOLTS", "BRAKE_CHECK"],
                "items": [
                    {"code": "INITIAL_INSPECTION", "name": "Kiểm tra tổng quát xe mới xuất xưởng"},
                    {"code": "CHASSIS_BOLTS", "name": "Siết lại toàn bộ ốc khung sườn và cổ phốt"},
                    {"code": "BRAKE_CHECK", "name": "Căn chỉnh độ rơ phanh trước/sau"},
                ],
            },
            {
                "odo": 5000,
                "months": 6,
                "name": "Mốc định kỳ 6 tháng / 5.000 - 10.000 km",
                "item_codes": [
                    "BRAKE_CHECK",
                    "CHASSIS_BOLTS",
                    "STEERING_GREASE",
                    "BATTERY_CHECK",
                    "TIRE_INSPECTION",
                    "FIRMWARE_UPDATE",
                ],
                "items": [
                    {
                        "code": "BRAKE_CHECK",
                        "name": "Kiểm tra má phanh, đĩa phanh và dầu phanh",
                        "action": "Vệ sinh cùm phanh, căn chỉnh",
                    },
                    {
                        "code": "CHASSIS_BOLTS",
                        "name": "Kiểm tra và siết lại ốc khung sườn, chân chống, giảm xóc",
                        "action": "Siết lực theo tiêu chuẩn",
                    },
                    {
                        "code": "STEERING_GREASE",
                        "name": "Kiểm tra độ rơ cổ phốt, tra mỡ bôi trơn bạc đạn",
                        "action": "Bôi trơn chống rỉ và kẹt",
                    },
                    {
                        "code": "BATTERY_CHECK",
                        "name": "Kiểm tra pin LFP, độ cân bằng cell và giắc sạc",
                        "action": "Đo thông số BMS",
                    },
                    {
                        "code": "TIRE_INSPECTION",
                        "name": "Đo áp suất lốp, kiểm tra độ mòn hoa lốp",
                        "action": "Bơm chuẩn áp suất 2.0 - 2.2 bar",
                    },
                    {
                        "code": "FIRMWARE_UPDATE",
                        "name": "Kiểm tra và cập nhật firmware ECU/BMS",
                        "action": "Cập nhật nếu có bản mới",
                    },
                ],
            },
            {
                "odo": 10000,
                "months": 12,
                "name": "Mốc lớn 12 tháng / 10.000 km",
                "item_codes": [
                    "BRAKE_FLUID_REPLACE",
                    "MOTOR_INSPECTION",
                    "CHASSIS_BOLTS",
                    "STEERING_GREASE",
                    "BATTERY_CHECK",
                    "TIRE_INSPECTION",
                ],
                "items": [
                    {"code": "BRAKE_FLUID_REPLACE", "name": "Thay dầu phanh DOT4"},
                    {"code": "MOTOR_INSPECTION", "name": "Kiểm tra động cơ In-hub và gioăng chống nước IP67"},
                    {"code": "CHASSIS_BOLTS", "name": "Siết lại toàn bộ ốc khung sườn"},
                    {"code": "STEERING_GREASE", "name": "Bảo dưỡng cổ phốt và bạc đạn bánh"},
                    {"code": "BATTERY_CHECK", "name": "Kiểm tra dung lượng và điện trở nội cell pin"},
                    {"code": "TIRE_INSPECTION", "name": "Đảo lốp hoặc khuyến nghị thay nếu mòn"},
                ],
            },
        ]
    },
    # Dòng ô tô điện (VF3, VF5, VF6, VF7, VF8, VF9, VFe34)
    "ev_car": {
        "milestones": [
            {
                "odo": 12000,
                "months": 12,
                "name": "Mốc 12.000 km hoặc 12 tháng",
                "item_codes": ["CABIN_FILTER", "BRAKE_CHECK", "HV_BATTERY_CHECK", "COOLANT_CHECK"],
                "items": [
                    {"code": "CABIN_FILTER", "name": "Vệ sinh/thay lọc gió điều hòa cabin"},
                    {"code": "BRAKE_CHECK", "name": "Kiểm tra hệ thống phanh tái sinh và phanh thủy lực"},
                    {"code": "HV_BATTERY_CHECK", "name": "Kiểm tra pin cao áp và độ cân bằng pack pin"},
                    {"code": "COOLANT_CHECK", "name": "Kiểm tra mức nước làm mát pin và biến tần"},
                ],
            },
            {
                "odo": 24000,
                "months": 24,
                "name": "Mốc 24.000 km hoặc 24 tháng",
                "item_codes": ["CABIN_FILTER_REPLACE", "BRAKE_FLUID_REPLACE", "COOLANT_REPLACE", "HV_BATTERY_CHECK"],
                "items": [
                    {"code": "CABIN_FILTER_REPLACE", "name": "Thay lọc gió điều hòa kháng khuẩn"},
                    {"code": "BRAKE_FLUID_REPLACE", "name": "Thay dầu phanh toàn phần"},
                    {"code": "COOLANT_REPLACE", "name": "Bổ sung dung dịch làm mát pin cao áp"},
                    {"code": "HV_BATTERY_CHECK", "name": "Chẩn đoán chuyên sâu hệ thống pin và motor điện"},
                ],
            },
        ]
    },
}


def _is_escooter(model: str) -> bool:
    m = model.strip().lower()
    return any(name in m for name in ["evo", "feliz", "klara", "theon", "vento", "impetus", "ludo", "tempest"])


@tool
def get_due_maintenance(
    model: str,
    current_odometer_km: int,
    months_since_last_service: int | None = None,
) -> dict[str, Any]:
    """Kiểm tra quy tắc bảo dưỡng định kỳ đến hạn của xe dựa trên số ODO và thời gian (số tháng kể từ lần bảo dưỡng trước).

    Quy tắc VinFast: Bảo dưỡng tính theo mốc km HOẶC mốc thời gian (tùy điều kiện nào đến trước).

    Args:
        model: Tên dòng xe (ví dụ: 'Evo200', 'Feliz S', 'VF5', 'VF8', 'VFe34')
        current_odometer_km: Số ODO hiện tại của xe (ví dụ: 5760)
        months_since_last_service: Số tháng kể từ lần bảo dưỡng gần nhất (ví dụ: 7)

    Returns:
        Thông tin chi tiết về tình trạng đến hạn, lý do kích hoạt, và danh sách mã hạng mục item_codes.
    """
    category = "escooter" if _is_escooter(model) else "ev_car"
    milestones = STANDARD_MAINTENANCE_RULES[category]["milestones"]

    # Phân tích theo mốc thời gian và ODO
    target_milestone = None
    is_overdue = False
    trigger_reason = ""

    if category == "escooter":
        # Chu kỳ bảo dưỡng xe máy điện VinFast là mỗi 6 tháng hoặc mỗi 5.000 km
        if months_since_last_service is not None and months_since_last_service >= 6:
            is_overdue = months_since_last_service > 6
            target_milestone = milestones[1]  # Mốc định kỳ 6 tháng
            trigger_reason = (
                f"Đã quá hạn định kỳ {months_since_last_service} tháng kể từ lần bảo dưỡng trước "
                f"(vượt quy định 6 tháng/lần của VinFast). "
                "Cần kiểm tra an toàn hệ thống phanh, tra mỡ cổ phốt và kiểm tra pin ngay cả khi số km đi ít."
            )
        elif current_odometer_km >= 9500:
            target_milestone = milestones[2]
            trigger_reason = f"Số ODO ({current_odometer_km:,} km) đã đạt mốc bảo dưỡng lớn 10.000 km."
        elif current_odometer_km >= 4500:
            target_milestone = milestones[1]
            trigger_reason = f"Số ODO ({current_odometer_km:,} km) đã đến hạn mốc 5.000 km."
        elif current_odometer_km >= 1000:
            target_milestone = milestones[0]
            trigger_reason = f"Số ODO ({current_odometer_km:,} km) đạt mốc kiểm tra ban đầu 1.000 km."
        else:
            target_milestone = milestones[0]
            trigger_reason = "Kiểm tra định kỳ ban đầu."
    else:
        # Ô tô điện VinFast: chu kỳ 12.000 km hoặc 12 tháng
        if months_since_last_service is not None and months_since_last_service >= 12:
            is_overdue = months_since_last_service > 12
            target_milestone = milestones[0]
            trigger_reason = (
                f"Đã quá hạn {months_since_last_service} tháng kể từ lần bảo dưỡng trước (chu kỳ 12 tháng)."
            )
        elif current_odometer_km >= 23000:
            target_milestone = milestones[1]
            trigger_reason = f"Số ODO ({current_odometer_km:,} km) đến mốc 24.000 km."
        else:
            target_milestone = milestones[0]
            trigger_reason = f"Số ODO ({current_odometer_km:,} km) đến mốc 12.000 km."

    return {
        "model": model,
        "current_odometer_km": current_odometer_km,
        "months_since_last_service": months_since_last_service,
        "is_due": True,
        "is_overdue": is_overdue,
        "due_milestone": target_milestone["name"],
        "trigger_reason": trigger_reason,
        "item_codes": target_milestone["item_codes"],
        "items": target_milestone["items"],
        "recommendation": (
            "Khuyến nghị đặt lịch bảo dưỡng sớm để đảm bảo an toàn kỹ thuật, "
            "tối ưu tuổi thọ pin và duy trì đầy đủ quyền lợi bảo hành chính hãng."
        ),
    }
