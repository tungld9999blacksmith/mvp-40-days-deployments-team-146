import asyncio
import os
import sys
from pathlib import Path

# Fix Windows console encoding for UTF-8
if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

os.environ["LANGCHAIN_TRACING_V2"] = "false"

# Add paths to sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir / "src"))

import pytest
from dotenv import load_dotenv

env_path = backend_dir.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

from src.agents.orchestrator import run_agent_turn


@pytest.mark.asyncio
async def test_evo200_demo_walkthrough():
    """Kịch bản Demo Flow từ README:
    Chủ xe Evo200 đi 5.760 km (cách lần trước 7 tháng).
    Hỏi: Cần làm gì, giá bao nhiêu? Đặt giúp lịch chiều thứ Bảy gần Thanh Xuân.
    """
    print("\n" + "=" * 60)
    print("BẮT ĐẦU KIỂM THỬ RUN_AGENT_TURN: KỊCH BẢN EVO200 WALKTHROUGH")
    print("=" * 60)

    vehicle_context = {
        "model": "Evo200",
        "current_odo": 5760,
        "last_service_odo": 5100,
        "months_since_last": 7,
        "license_plate": "29-AA 123.45",
    }

    user_message = (
        "Xe Evo200 của tôi đi 5.760 km, lần bảo dưỡng trước là 5.100 km cách đây 7 tháng. "
        "Tôi cần làm gì và chi phí bao nhiêu? Đặt giúp lịch chiều thứ Bảy ở gần Thanh Xuân."
    )

    tools_called = []
    tokens = []
    completed_data = None

    print(f"\n[CHỦ XE]: {user_message}\n")
    print("[AI ORCHESTRATOR STREAMING]:")

    async for event in run_agent_turn(
        conversation_id="conv-demo-01",
        user_id="user-evo-01",
        vehicle_id="vh-evo-01",
        message=user_message,
        vehicle_context=vehicle_context,
    ):
        event_type = event["type"]

        if event_type == "tool_start":
            tool_name = event["tool"]
            tools_called.append(tool_name)
            print(f"\n⚙️ [GỌI TOOL]: {tool_name} (Inputs: {event.get('input')})")

        elif event_type == "tool_end":
            print(f"   ✓ [TOOL HOÀN TẤT]: {event['tool']}")

        elif event_type == "token":
            delta = event["delta"]
            tokens.append(delta)
            print(delta, end="", flush=True)

        elif event_type == "completed":
            completed_data = event["message_data"]
            print("\n\n🏁 [HOÀN TẤT LƯỢT HỘI THOẠI]")

    full_response = "".join(tokens) or (completed_data["content"] if completed_data else "")

    print("\n" + "-" * 60)
    print("KIỂM TRA CÁC RÀNG BUỘC THEO THIẾT KẾ README:")
    print("-" * 60)

    # 1. Kiểm tra tool gọi
    print(f"1. Danh sách tool đã gọi: {tools_called}")
    assert "get_due_maintenance" in tools_called, "Phải gọi get_due_maintenance đầu tiên"
    assert "estimate_service_cost" in tools_called, "Phải gọi estimate_service_cost"
    assert "find_workshops" in tools_called, "Phải gọi find_workshops khi tìm xưởng gần Thanh Xuân"

    # 2. Kiểm tra thứ tự gọi tool
    idx_maint = tools_called.index("get_due_maintenance")
    idx_cost = tools_called.index("estimate_service_cost")
    assert idx_maint < idx_cost, "get_due_maintenance phải được gọi TRƯỚC estimate_service_cost"
    print("   ✓ Thứ tự gọi tool chính xác: get_due_maintenance -> estimate_service_cost")

    # 3. Ràng buộc an toàn: Chưa được tự ý tạo đơn giữ chỗ
    assert "create_booking_draft" not in tools_called, (
        "create_booking_draft KHÔNG ĐƯỢC gọi khi chủ xe chưa xác nhận khung giờ cụ thể!"
    )
    print("   ✓ Bảo đảm an toàn: Chưa gọi create_booking_draft (chờ chủ xe chốt giờ)")

    # 4. Kiểm tra nội dung phản hồi
    resp_lower = full_response.lower()
    has_maint_info = any(k in resp_lower for k in ["bảo dưỡng", "quá hạn", "7 tháng", "6 tháng"])
    has_cost_info = any(k in resp_lower for k in ["chi phí", "giá", "miễn phí", "150", "250", "tiền công"])
    has_slot_info = any(k in resp_lower for k in ["chiều thứ bảy", "thứ bảy", "14:00", "15:30", "16:30", "khung giờ"])

    assert has_maint_info, "Phản hồi phải giải thích lý do quá hạn / mốc bảo dưỡng"
    assert has_cost_info, "Phản hồi phải có dự toán chi phí"
    assert has_slot_info, "Phản hồi phải đề xuất khung giờ / xưởng"

    print("   ✓ Phản hồi đầy đủ thông tin: Lý do quá hạn, dự toán chi phí và đề xuất khung giờ!")
    print("\n>>> TEST KỊCH BẢN EVO200 THÀNH CÔNG RỰC RỠ! <<<\n")


if __name__ == "__main__":
    asyncio.run(test_evo200_demo_walkthrough())
