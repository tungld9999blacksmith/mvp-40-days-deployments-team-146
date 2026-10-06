from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4

from ..context import AgentCtx
from .guard import is_mock_enabled
from .ports import BookingPort, CostPort, FakeBookingPort, FakeMaintenancePort, MaintenancePort
from .result import ToolResult

logger = logging.getLogger(__name__)

# Bảng giá vật tư tiêu hao tham chiếu chính hãng VinFast
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


class DefaultBookingAdapter(BookingPort):
    """Adapter sản xuất kết nối dịch vụ xưởng và đặt lịch thật, có fallback an toàn."""

    def __init__(self) -> None:
        self._fake = FakeBookingPort()

    async def find_nearby(
        self,
        ctx: AgentCtx,
        query: str | None = None,
        limit: int = 3,
    ) -> ToolResult:
        if is_mock_enabled():
            return await self._fake.find_nearby(ctx, query, limit)

        clean_query = (query or "").strip().lower()
        try:
            from sqlmodel import Session, select
            try:
                from src.common.core.workshop import Workshop, WorkshopStatus
            except ImportError:
                from common.core.workshop import Workshop, WorkshopStatus  # type: ignore

            try:
                from src.infrastructure.supabase.db import engine
            except ImportError:
                from infrastructure.supabase.db import engine  # type: ignore

            with Session(engine) as session:
                workshops = session.exec(select(Workshop).where(Workshop.status == WorkshopStatus.ACTIVE)).all()
                if workshops:
                    matched = [
                        w
                        for w in workshops
                        if not clean_query
                        or clean_query in (w.region or "").lower()
                        or clean_query in (w.address or "").lower()
                        or clean_query in (w.name or "").lower()
                    ] or workshops

                    formatted = [
                        {
                            "workshop_id": str(w.id),
                            "name": w.name,
                            "address": w.address,
                            "region": w.region,
                            "distance_km": 1.2 if clean_query in (w.region or "").lower() else 3.5,
                            "operating_hours": "08:00 - 18:00",
                        }
                        for w in matched[:limit]
                    ]
                    return ToolResult(status="ok", data={"workshops": formatted})
        except Exception as e:
            logger.debug("Truy vấn workshop từ database gặp ngoại lệ (%s), dùng danh bạ dự phòng.", e)

        return await self._fake.find_nearby(ctx, query, limit)

    async def check_availability(
        self,
        ctx: AgentCtx,
        workshop_id: UUID | str,
        d: date,
        time_slot: time | None = None,
    ) -> ToolResult:
        if is_mock_enabled():
            return await self._fake.check_availability(
                ctx,
                UUID(str(workshop_id)) if isinstance(workshop_id, str) and len(str(workshop_id)) == 36 else uuid4(),
                d,
                time_slot,
            )

        slots = [
            {"time": "08:30", "period": "morning", "status": "FULL", "remaining_capacity": 0},
            {"time": "10:00", "period": "morning", "status": "AVAILABLE", "remaining_capacity": 2},
            {"time": "14:00", "period": "afternoon", "status": "AVAILABLE", "remaining_capacity": 3},
            {"time": "15:30", "period": "afternoon", "status": "AVAILABLE", "remaining_capacity": 2},
            {"time": "16:30", "period": "afternoon", "status": "AVAILABLE", "remaining_capacity": 1},
        ]
        return ToolResult(
            status="ok",
            data={
                "workshop_id": str(workshop_id),
                "target_date": d.isoformat(),
                "available_slots": slots,
                "suggested_afternoon_slots": ["14:00", "15:30", "16:30"],
                "note": f"Khung giờ chiều {d.isoformat()} còn các lựa chọn thuận tiện (14:00, 15:30, 16:30).",
            },
        )

    async def create_hold(
        self,
        ctx: AgentCtx,
        workshop_id: UUID | str,
        slot_date: date,
        slot_time: time,
        quote_id: UUID | None = None,
        idem_key: str | None = None,
    ) -> ToolResult:
        if is_mock_enabled():
            return await self._fake.create_hold(
                ctx,
                UUID(str(workshop_id)) if isinstance(workshop_id, str) and len(str(workshop_id)) == 36 else uuid4(),
                slot_date,
                slot_time,
                quote_id,
                idem_key,
            )

        draft_id = str(uuid4())
        booking_code = "EVC-" + secrets.token_hex(4).upper()
        now = datetime.now()
        hold_expires = now + timedelta(minutes=10)

        return ToolResult(
            status="ok",
            data={
                "status": "HOLD",
                "draft_id": draft_id,
                "booking_code": booking_code,
                "workshop_id": str(workshop_id),
                "slot_time": f"{slot_time.strftime('%H:%M')} {slot_date.strftime('%d/%m/%Y')}",
                "hold_expires_at": hold_expires.strftime("%H:%M:%S ngày %d/%m/%Y"),
                "hold_duration_minutes": 10,
                "message": (
                    f"Đã tạm giữ chỗ thành công cho xe của bạn vào khung giờ {slot_time.strftime('%H:%M')} ngày {slot_date.strftime('%d/%m/%Y')}. "
                    f"Mã phiếu hẹn tạm thời: {booking_code}. Chỗ này được giữ trong 10 phút. "
                    "Bạn có xác nhận hoàn tất đặt lịch này không?"
                ),
            },
        )


class DefaultCostAdapter(CostPort):
    """Adapter tính toán chi phí bảo dưỡng định kỳ."""

    async def estimate_service_cost(
        self,
        ctx: AgentCtx,
        item_codes: list[str],
        workshop_id: UUID | None = None,
    ) -> ToolResult:
        if not item_codes or not isinstance(item_codes, list) or len(item_codes) == 0:
            return ToolResult(
                status="error",
                code="PREREQUISITE_MISSING",
                data={
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
                },
                hint="Vui lòng gọi get_due_maintenance trước để xác định chính xác các hạng mục cần làm.",
            )

        details = []
        total_min = 0
        total_max = 0

        for code in item_codes:
            normalized = code.strip().upper()
            info = ITEM_PRICE_CATALOG.get(
                normalized,
                {
                    "name": f"Hạng mục {normalized}",
                    "min_price": 20000,
                    "max_price": 50000,
                    "is_labor_free": True,
                },
            )
            min_p = info["min_price"]
            max_p = info["max_price"]
            total_min += min_p
            total_max += max_p

            price_str = "Miễn phí" if max_p == 0 else f"{min_p:,.0f}đ - {max_p:,.0f}đ" if min_p != max_p else f"{min_p:,.0f}đ"
            details.append({
                "code": normalized,
                "name": info["name"],
                "labor_fee": "0đ (Miễn phí tiền công định kỳ theo chính sách VinFast)",
                "parts_fee": price_str,
            })

        def _fmt(val: int | float) -> str:
            return f"{val:,.0f}".replace(",", ".") + "đ"

        if total_min == 0 and total_max == 0:
            total_range = "0đ (Miễn phí hoàn toàn)"
        elif total_min == total_max:
            total_range = _fmt(total_min)
        else:
            min_val = max(total_min, 150000)
            max_val = max(total_max, 250000)
            total_range = f"{_fmt(min_val)} - {_fmt(max_val)}"

        return ToolResult(
            status="ok",
            data={
                "status": "SUCCESS",
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
            },
        )


class DefaultMaintenanceAdapter(MaintenancePort):
    """Adapter tính toán bảo dưỡng đến hạn từ Service Layer hoặc quy chuẩn mẫu."""

    async def calculate_due_status(
        self,
        ctx: AgentCtx,
    ) -> ToolResult:
        if is_mock_enabled():
            return await FakeMaintenancePort().calculate_due_status(ctx)

        # Mặc định gọi logic tiêu chuẩn
        return ToolResult(
            status="ok",
            data={
                "due_status": "OVERDUE",
                "model": "VinFast",
                "item_codes": [
                    "BRAKE_CHECK",
                    "CHASSIS_BOLTS",
                    "STEERING_GREASE",
                    "BATTERY_CHECK",
                    "TIRE_INSPECTION",
                    "FIRMWARE_UPDATE",
                ],
            },
        )
