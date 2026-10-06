from __future__ import annotations

from datetime import date, time
from typing import Any, Protocol
from uuid import UUID

from ..context import AgentCtx
from .result import ToolResult


class BookingPort(Protocol):
    """Port interface cho các dịch vụ tìm xưởng, kiểm tra giờ trống và giữ chỗ."""

    async def find_nearby(
        self,
        ctx: AgentCtx,
        query: str | None = None,
        limit: int = 3,
    ) -> ToolResult: ...

    async def check_availability(
        self,
        ctx: AgentCtx,
        workshop_id: UUID,
        d: date,
        time_slot: time | None = None,
    ) -> ToolResult: ...

    async def create_hold(
        self,
        ctx: AgentCtx,
        workshop_id: UUID,
        slot_date: date,
        slot_time: time,
        quote_id: UUID | None = None,
        idem_key: str | None = None,
    ) -> ToolResult: ...


class CostPort(Protocol):
    """Port interface cho dự toán chi phí bảo dưỡng."""

    async def estimate_service_cost(
        self,
        ctx: AgentCtx,
        item_codes: list[str],
        workshop_id: UUID | None = None,
    ) -> ToolResult: ...


class MaintenancePort(Protocol):
    """Port interface cho tính toán mốc và hạng mục bảo dưỡng đến hạn."""

    async def calculate_due_status(
        self,
        ctx: AgentCtx,
    ) -> ToolResult: ...


# ==============================================================================
# FAKE PORTS CHO UNIT TESTS CÔ LẬP (Không cần DB / Redis)
# ==============================================================================


class FakeBookingPort:
    """Fake implementation của BookingPort phục vụ kiểm thử nhanh."""

    def __init__(self, workshops: list[dict[str, Any]] | None = None) -> None:
        self.workshops = workshops or [
            {
                "workshop_id": "ws-thanh-xuan-01",
                "name": "Xưởng Dịch vụ VinFast Thanh Xuân",
                "address": "Số 68 Lê Văn Lương, Phường Nhân Chính, Quận Thanh Xuân, Hà Nội",
                "region": "Thanh Xuân",
                "distance_km": 1.2,
                "operating_hours": "08:00 - 18:00",
            }
        ]

    async def find_nearby(
        self,
        ctx: AgentCtx,
        query: str | None = None,
        limit: int = 3,
    ) -> ToolResult:
        matched = [
            w for w in self.workshops
            if not query or query.lower() in w["region"].lower() or query.lower() in w["address"].lower()
        ] or self.workshops
        return ToolResult(
            status="ok" if matched else "empty",
            data={"workshops": matched[:limit]},
            hint="Không tìm thấy xưởng phù hợp tại khu vực này." if not matched else None,
        )

    async def check_availability(
        self,
        ctx: AgentCtx,
        workshop_id: UUID,
        d: date,
        time_slot: time | None = None,
    ) -> ToolResult:
        slots = [
            {"time": "14:00", "available": True, "remaining": 3},
            {"time": "15:30", "available": True, "remaining": 2},
            {"time": "16:30", "available": True, "remaining": 1},
        ]
        return ToolResult(
            status="ok",
            data={
                "workshop_id": str(workshop_id),
                "date": d.isoformat(),
                "available_slots": slots,
            },
        )

    async def create_hold(
        self,
        ctx: AgentCtx,
        workshop_id: UUID,
        slot_date: date,
        slot_time: time,
        quote_id: UUID | None = None,
        idem_key: str | None = None,
    ) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "booking_code": "EVC-TEST1234",
                "status": "pending",
                "workshop_id": str(workshop_id),
                "date": slot_date.isoformat(),
                "time": slot_time.isoformat(),
                "hold_duration_minutes": 10,
            },
        )


class FakeCostPort:
    """Fake implementation của CostPort phục vụ kiểm thử nhanh."""

    async def estimate_service_cost(
        self,
        ctx: AgentCtx,
        item_codes: list[str],
        workshop_id: UUID | None = None,
    ) -> ToolResult:
        if not item_codes:
            return ToolResult(
                status="error",
                code="DATA_INCOMPLETE",
                hint="Vui lòng kiểm tra các hạng mục bảo dưỡng trước khi dự toán chi phí.",
            )
        return ToolResult(
            status="ok",
            data={
                "model": "Evo200",
                "item_count": len(item_codes),
                "min_total": 150000,
                "max_total": 250000,
                "is_labor_free": True,
            },
        )


class FakeMaintenancePort:
    """Fake implementation của MaintenancePort phục vụ kiểm thử nhanh."""

    def __init__(self, due_status: str = "OVERDUE") -> None:
        self.due_status = due_status

    async def calculate_due_status(
        self,
        ctx: AgentCtx,
    ) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "due_status": self.due_status,
                "model": "Evo200",
                "current_odo": 5760,
                "months_since_last": 7,
                "milestone_km": 5000,
                "milestone_months": 6,
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


# ==============================================================================
# GLOBAL PORT REGISTRY & DEPENDENCY INJECTION
# ==============================================================================

_booking_port: BookingPort | None = None
_cost_port: CostPort | None = None
_maintenance_port: MaintenancePort | None = None


def get_booking_port() -> BookingPort:
    global _booking_port
    if _booking_port is None:
        try:
            from .adapters import DefaultBookingAdapter
            _booking_port = DefaultBookingAdapter()
        except ImportError:
            _booking_port = FakeBookingPort()
    return _booking_port


def set_booking_port(port: BookingPort | None) -> None:
    global _booking_port
    _booking_port = port


def get_cost_port() -> CostPort:
    global _cost_port
    if _cost_port is None:
        try:
            from .adapters import DefaultCostAdapter
            _cost_port = DefaultCostAdapter()
        except ImportError:
            _cost_port = FakeCostPort()
    return _cost_port


def set_cost_port(port: CostPort | None) -> None:
    global _cost_port
    _cost_port = port


def get_maintenance_port() -> MaintenancePort:
    global _maintenance_port
    if _maintenance_port is None:
        try:
            from .adapters import DefaultMaintenanceAdapter
            _maintenance_port = DefaultMaintenanceAdapter()
        except ImportError:
            _maintenance_port = FakeMaintenancePort()
    return _maintenance_port


def set_maintenance_port(port: MaintenancePort | None) -> None:
    global _maintenance_port
    _maintenance_port = port

