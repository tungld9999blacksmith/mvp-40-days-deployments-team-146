from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from src.agents.context import AgentCtx
from src.agents.tools.guard import tool_guard
from src.agents.tools.ports import (
    FakeBookingPort,
    FakeCostPort,
    FakeMaintenancePort,
    get_booking_port,
    get_cost_port,
    get_maintenance_port,
    set_booking_port,
    set_cost_port,
    set_maintenance_port,
)
from src.agents.tools.resolve_date import WEEKDAY_MAP, ResolvedDate, resolve_date
from src.agents.tools.result import ToolResult

# ==============================================================================
# 1. KIỂM THỬ TOOLRESULT (CONTRACT & COMPATIBILITY)
# ==============================================================================


def test_tool_result_contract_and_for_llm():
    """Kiểm tra format JSON chuẩn mực cho LLM qua for_llm()."""
    res = ToolResult(
        status="ok",
        code="SUCCESS",
        data={"model": "Evo200", "milestone_km": 5000},
        hint="Đã tra cứu thành công",
    )
    llm_str = res.for_llm()
    assert '"status": "ok"' in llm_str
    assert '"code": "SUCCESS"' in llm_str
    assert '"model": "Evo200"' in llm_str
    assert '"hint": "Đã tra cứu thành công"' in llm_str


def test_tool_result_backwards_compatibility():
    """Kiểm tra tính tương thích ngược: indexing, iteration, len, get."""
    # Test với data dict
    res_dict = ToolResult(
        status="ok",
        data={"model": "VF8", "item_codes": ["BRAKE_CHECK", "BATTERY_CHECK"]},
    )
    assert res_dict["model"] == "VF8"
    assert "BRAKE_CHECK" in res_dict["item_codes"]
    assert res_dict.get("model") == "VF8"
    assert res_dict.get("non_existent", "default_val") == "default_val"
    assert "model" in res_dict

    # Test với data list workshops
    res_list = ToolResult(
        status="ok",
        data={
            "workshops": [
                {"name": "Xưởng A", "distance_km": 1.2},
                {"name": "Xưởng B", "distance_km": 2.5},
            ]
        },
    )
    assert len(res_list) == 2
    assert res_list[0]["name"] == "Xưởng A"
    assert res_list[1]["distance_km"] == 2.5
    assert [w["name"] for w in res_list] == ["Xưởng A", "Xưởng B"]

    # Test ưu tiên payload status
    res_error_status = ToolResult(
        status="error",
        data={"status": "ERROR_PREREQUISITE_MISSING", "error_type": "ToolDependencyError"},
    )
    assert res_error_status["status"] == "ERROR_PREREQUISITE_MISSING"


# ==============================================================================
# 2. KIỂM THỬ TOOL_GUARD (TIMEOUT & ERROR RESILIENCE)
# ==============================================================================


def test_tool_guard_sync_success_and_exception():
    """Kiểm tra @tool_guard bọc hàm đồng bộ bắt ngoại lệ an toàn."""
    @tool_guard(tool_name="test_sync_success")
    def sync_success():
        return {"data": 123}

    result = sync_success()
    assert isinstance(result, ToolResult)
    assert result.status == "ok"
    assert result["data"] == 123

    @tool_guard(tool_name="test_sync_fail", default_hint="Gợi ý an toàn khi lỗi")
    def sync_fail():
        raise RuntimeError("Database connection lost")

    fail_result = sync_fail()
    assert isinstance(fail_result, ToolResult)
    assert fail_result.status == "error"
    assert fail_result.code == "INTERNAL_ERROR"
    assert fail_result.hint == "Gợi ý an toàn khi lỗi"


@pytest.mark.asyncio
async def test_tool_guard_async_timeout():
    """Kiểm tra @tool_guard quản lý timeout cho hàm bất đồng bộ."""
    @tool_guard(tool_name="test_async_timeout", timeout_seconds=0.1)
    async def slow_async():
        await asyncio.sleep(0.5)
        return {"done": True}

    timeout_res = await slow_async()
    assert isinstance(timeout_res, ToolResult)
    assert timeout_res.status == "error"
    assert timeout_res.code == "TIMEOUT"
    assert "vượt quá giới hạn cho phép" in (timeout_res.hint or "")


# ==============================================================================
# 3. KIỂM THỬ PURE RESOLVE_DATE (XỬ LÝ NGÀY TỰ NHIÊN TIẾNG VIỆT)
# ==============================================================================


def test_resolve_date_iso_and_vietnamese_format():
    """Kiểm tra phân giải định dạng ISO và định dạng ngày/tháng Việt Nam."""
    fixed_now = datetime(2026, 10, 3, 10, 0, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))

    # ISO
    res_iso = resolve_date("2026-10-15", now=fixed_now)
    assert res_iso is not None
    assert res_iso.target_date == date(2026, 10, 15)

    # DD/MM/YYYY
    res_dmy = resolve_date("20/11/2026", now=fixed_now)
    assert res_dmy is not None
    assert res_dmy.target_date == date(2026, 11, 20)


def test_resolve_date_relative_keywords():
    """Kiểm tra các từ khóa tương đối: hôm nay, ngày mai, ngày kia."""
    fixed_now = datetime(2026, 10, 3, 10, 0, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))

    res_today = resolve_date("Đặt lịch hôm nay", now=fixed_now)
    assert res_today is not None
    assert res_today.target_date == date(2026, 10, 3)

    res_tomorrow = resolve_date("sáng mai", now=fixed_now)
    assert res_tomorrow is not None
    assert res_tomorrow.target_date == date(2026, 10, 4)
    assert res_tomorrow.session == "morning"

    res_after = resolve_date("ngày kia", now=fixed_now)
    assert res_after is not None
    assert res_after.target_date == date(2026, 10, 5)


def test_resolve_date_weekday_and_afternoon():
    """Kiểm tra yêu cầu từ user 'chiều thứ Bảy': không gán giờ cứng, nhận diện buổi chiều."""
    # Giả định hiện tại là Thứ Năm ngày 01/10/2026 (weekday=3)
    fixed_thursday = datetime(2026, 10, 1, 10, 0, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    res = resolve_date("chiều thứ Bảy", now=fixed_thursday)
    assert res is not None
    # Thứ Bảy gần nhất là ngày 03/10/2026
    assert res.target_date == date(2026, 10, 3)
    assert res.session == "afternoon"
    # Quan trọng: không tự gán một giờ cố định
    assert res.target_time is None


def test_resolve_date_specific_time():
    """Kiểm tra khi người dùng nêu giờ cụ thể: 14h, 15:30."""
    res_time = resolve_date("14h30 thứ 7")
    assert res_time is not None
    assert res_time.target_time == time(14, 30)


# ==============================================================================
# 4. KIỂM THỬ AGENTCTX VÀ DEPENDENCY INJECTION CHO PORTS
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_ctx_and_port_di():
    """Kiểm tra Dependency Injection cho Ports thông qua Fake Ports."""
    ctx = AgentCtx(
        user_id=101,
        vehicle_id=uuid4(),
        conversation_id=uuid4(),
        operation_key="op-test-key-123",
    )

    # 1. Test FakeBookingPort qua Registry
    custom_ws = [{"workshop_id": "ws-custom", "name": "Xưởng Test", "region": "Cầu Giấy", "distance_km": 0.5}]
    fake_booking = FakeBookingPort(workshops=custom_ws)
    set_booking_port(fake_booking)
    active_b_port = get_booking_port()

    res_nearby = await active_b_port.find_nearby(ctx, query="Cầu Giấy")
    assert res_nearby.status == "ok"
    assert len(res_nearby["workshops"]) == 1
    assert res_nearby["workshops"][0]["name"] == "Xưởng Test"

    # 2. Test FakeCostPort qua Registry
    fake_cost = FakeCostPort()
    set_cost_port(fake_cost)
    active_c_port = get_cost_port()

    cost_res = await active_c_port.estimate_service_cost(ctx, item_codes=["BRAKE_CHECK"])
    assert cost_res.status == "ok"
    assert cost_res["is_labor_free"] is True

    # 3. Test FakeMaintenancePort qua Registry
    fake_maint = FakeMaintenancePort(due_status="DUE_SOON")
    set_maintenance_port(fake_maint)
    active_m_port = get_maintenance_port()

    maint_res = await active_m_port.calculate_due_status(ctx)
    assert maint_res.status == "ok"
    assert maint_res["due_status"] == "DUE_SOON"

    # Reset ports về mặc định
    set_booking_port(None)
    set_cost_port(None)
    set_maintenance_port(None)
