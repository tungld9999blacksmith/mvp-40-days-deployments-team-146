import sys
from pathlib import Path

# Fix Windows console encoding for UTF-8
if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

# Add paths to sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir / "src"))

from src.agents.tools import (
    create_booking_draft,
    estimate_service_cost,
    find_workshops,
    get_available_slots,
    get_due_maintenance,
)


def test_get_due_maintenance_evo200_overdue():
    """Kiểm tra quy tắc bảo dưỡng ODO 5.760 km, 7 tháng trước -> Quá hạn mốc 6 tháng."""
    result = get_due_maintenance.invoke(
        {
            "model": "Evo200",
            "current_odometer_km": 5760,
            "months_since_last_service": 7,
        }
    )

    assert result["model"] == "Evo200"
    assert result["current_odometer_km"] == 5760
    assert result["months_since_last_service"] == 7
    assert result["is_due"] is True
    assert result["is_overdue"] is True
    assert "7 tháng" in result["trigger_reason"]
    assert "BRAKE_CHECK" in result["item_codes"]
    assert "STEERING_GREASE" in result["item_codes"]
    assert "CHASSIS_BOLTS" in result["item_codes"]
    assert "BATTERY_CHECK" in result["item_codes"]
    print("PASS: test_get_due_maintenance_evo200_overdue")


def test_estimate_service_cost_guardrail_dependency_error():
    """Kiểm tra cơ chế Self-Correction khi gọi estimate_service_cost không có item_codes."""
    result = estimate_service_cost.invoke(
        {
            "model": "Evo200",
            "item_codes": [],
        }
    )

    assert result["status"] == "ERROR_PREREQUISITE_MISSING"
    assert result["error_type"] == "ToolDependencyError"
    assert result["action_required"] == "call get_due_maintenance first"
    assert "CẢNH BÁO THỨ TỰ GỌI CÔNG CỤ" in result["message"]
    print("PASS: test_estimate_service_cost_guardrail_dependency_error")


def test_estimate_service_cost_with_valid_items():
    """Kiểm tra tính chi phí: Tiền công miễn phí 100%, vật tư trong dải 150k - 250k."""
    item_codes = ["BRAKE_CHECK", "STEERING_GREASE", "CHASSIS_BOLTS", "BATTERY_CHECK"]
    result = estimate_service_cost.invoke(
        {
            "model": "Evo200",
            "item_codes": item_codes,
        }
    )

    assert result["status"] == "SUCCESS"
    assert result["labor_cost"] == 0
    assert "150.000" in result["estimated_total"]
    assert "250.000" in result["estimated_total"]
    assert result["item_count"] == 4
    print("PASS: test_estimate_service_cost_with_valid_items")


def test_find_workshops_and_slots():
    """Kiểm tra CQRS Read Tools: Tìm xưởng ở Thanh Xuân và lấy khung giờ chiều thứ Bảy."""
    # 1. Tìm xưởng
    workshops = find_workshops.invoke({"area_or_address": "Thanh Xuân", "limit": 2})
    assert len(workshops) > 0
    top_ws = workshops[0]
    assert "Thanh Xuân" in top_ws["name"]
    assert top_ws["distance_km"] <= 1.5

    # 2. Lấy khung giờ
    slots_info = get_available_slots.invoke(
        {
            "workshop_id": top_ws["workshop_id"],
            "target_date": "Thứ Bảy",
        }
    )
    assert slots_info["workshop_id"] == top_ws["workshop_id"]
    assert "14:00" in slots_info["suggested_afternoon_slots"]
    assert "15:30" in slots_info["suggested_afternoon_slots"]
    print("PASS: test_find_workshops_and_slots")


def test_create_booking_draft_hold():
    """Kiểm tra CQRS Write Tool: Tạo bản nháp giữ chỗ HOLD trong 10 phút."""
    draft = create_booking_draft.invoke(
        {
            "workshop_id": "ws-thanh-xuan-01",
            "slot_time": "14:00 Thứ Bảy 03/10",
            "service_items": ["Bảo dưỡng định kỳ 6 tháng", "Kiểm tra phanh và cổ phốt"],
        }
    )

    assert draft["status"] == "HOLD"
    assert draft["booking_code"].startswith("EVC-")
    assert draft["hold_duration_minutes"] == 10
    assert "14:00" in draft["slot_time"]
    print("PASS: test_create_booking_draft_hold")


if __name__ == "__main__":
    test_get_due_maintenance_evo200_overdue()
    test_estimate_service_cost_guardrail_dependency_error()
    test_estimate_service_cost_with_valid_items()
    test_find_workshops_and_slots()
    test_create_booking_draft_hold()
    print("\nALL TOOLS UNIT TESTS PASSED!")
