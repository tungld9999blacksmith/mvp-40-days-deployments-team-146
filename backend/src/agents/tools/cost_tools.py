from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Đơn giá tham chiếu vật tư phụ tùng tiêu hao chính hãng VinFast
ITEM_PRICE_CATALOG: dict[str, dict[str, Any]] = {
    "STEERING_GREASE": {
        "name": "Mỡ bôi trơn cổ phốt & bạc đạn chuyên dụng",
        "min_price": 50000,
        "max_price": 80000,
        "is_labor_free": True,
    },
    "BRAKE_CHECK": {
        "name": "Dung dịch vệ sinh và bảo dưỡng cùm phanh",
        "min_price": 60000,
        "max_price": 90000,
        "is_labor_free": True,
    },
    "CHASSIS_BOLTS": {
        "name": "Siết ốc khung gầm theo lực tiêu chuẩn",
        "min_price": 0,
        "max_price": 0,
        "is_labor_free": True,
    },
    "BATTERY_CHECK": {
        "name": "Đo chẩn đoán dung lượng pin và BMS",
        "min_price": 0,
        "max_price": 0,
        "is_labor_free": True,
    },
    "TIRE_INSPECTION": {
        "name": "Kiểm tra và bơm chuẩn áp suất lốp",
        "min_price": 0,
        "max_price": 0,
        "is_labor_free": True,
    },
    "FIRMWARE_UPDATE": {
        "name": "Cập nhật firmware phần mềm chính hãng",
        "min_price": 0,
        "max_price": 0,
        "is_labor_free": True,
    },
    "BRAKE_FLUID_REPLACE": {
        "name": "Dầu phanh DOT4 chính hãng",
        "min_price": 100000,
        "max_price": 150000,
        "is_labor_free": True,
    },
    "CABIN_FILTER": {
        "name": "Lọc gió điều hòa kháng khuẩn",
        "min_price": 250000,
        "max_price": 350000,
        "is_labor_free": True,
    },
    "COOLANT_CHECK": {
        "name": "Kiểm tra và châm nước làm mát pin",
        "min_price": 50000,
        "max_price": 100000,
        "is_labor_free": True,
    },
}


@tool
def estimate_service_cost(
    model: str,
    item_codes: list[str],
    workshop_id: str | None = None,
) -> dict[str, Any]:
    """Dự toán chi phí bảo dưỡng định kỳ dựa trên danh sách mã hạng mục item_codes.

    ⚠️ RÀNG BUỘC PHỤ THUỘC (GUARDRAIL):
    Công cụ này bắt buộc phải nhận danh sách `item_codes` từ kết quả của `get_due_maintenance`.
    Không được tự đoán giá hoặc gọi tool này khi chưa có `item_codes`.

    Args:
        model: Tên dòng xe (ví dụ: 'Evo200', 'VF5', 'VF8')
        item_codes: Danh sách mã hạng mục bảo dưỡng (ví dụ: ['BRAKE_CHECK', 'CHASSIS_BOLTS', 'STEERING_GREASE', ...])
        workshop_id: Mã xưởng dịch vụ (tùy chọn)

    Returns:
        Dự toán chi phí tiền công (miễn phí theo bảo hành), chi phí vật tư và tổng ước tính.
    """
    # ── Guardrail: Kiểm tra tính phụ thuộc ────────────────────────────────
    if not item_codes or not isinstance(item_codes, list) or len(item_codes) == 0:
        return {
            "status": "ERROR_PREREQUISITE_MISSING",
            "error_type": "ToolDependencyError",
            "message": (
                "⚠️ CẢNH BÁO THỨ TỰ GỌI CÔNG CỤ: "
                "Tool `estimate_service_cost` bắt buộc phải có danh sách mã hạng mục `item_codes` "
                "từ kết quả của tool `get_due_maintenance`. "
                "Vui lòng gọi `get_due_maintenance` trước để xác định chính xác các hạng mục bảo dưỡng, "
                "sau đó truyền `item_codes` vào công cụ này!"
            ),
            "action_required": "call get_due_maintenance first",
        }

    # Tính toán chi phí
    details = []
    total_min = 0
    total_max = 0

    for code in item_codes:
        normalized_code = code.strip().upper()
        item_info = ITEM_PRICE_CATALOG.get(
            normalized_code,
            {
                "name": f"Hạng mục {normalized_code}",
                "min_price": 20000,
                "max_price": 50000,
                "is_labor_free": True,
            },
        )
        min_p = item_info["min_price"]
        max_p = item_info["max_price"]
        total_min += min_p
        total_max += max_p

        price_display = (
            "Miễn phí" if max_p == 0 else f"{min_p:,.0f}đ - {max_p:,.0f}đ" if min_p != max_p else f"{min_p:,.0f}đ"
        )

        details.append(
            {
                "code": normalized_code,
                "name": item_info["name"],
                "labor_fee": "0đ (Miễn phí tiền công định kỳ theo chính sách VinFast)",
                "parts_fee": price_display,
            }
        )

    def _fmt(val: int | float) -> str:
        return f"{val:,.0f}".replace(",", ".") + "đ"

    # Đảm bảo dải giá tiêu hao tối thiểu cho các mốc định kỳ có vật tư
    if total_min == 0 and total_max == 0:
        total_range = "0đ (Miễn phí hoàn toàn)"
    elif total_min == total_max:
        total_range = _fmt(total_min)
    else:
        # Dải tiêu hao chuẩn cho mốc định kỳ có phát sinh phụ tư
        min_val = max(total_min, 150000)
        max_val = max(total_max, 250000)
        total_range = f"{_fmt(min_val)} - {_fmt(max_val)}"

    return {
        "status": "SUCCESS",
        "model": model,
        "item_count": len(item_codes),
        "labor_cost": 0,
        "labor_policy": "Miễn phí 100% tiền công bảo dưỡng định kỳ theo chính sách bảo hành VinFast",
        "estimated_total": total_range,
        "currency": "VND",
        "details": details,
        "note": (
            "Tiền công được miễn phí theo chế độ bảo hành định kỳ VinFast. "
            "Chi phí ước tính bao gồm vật tư tiêu hao (như mỡ bôi trơn cổ phốt chuyên dụng, "
            "dung dịch làm sạch phanh). Chi phí thực tế có thể thay đổi nhẹ tùy theo hiện trạng thực tế của xe tại xưởng."
        ),
    }
