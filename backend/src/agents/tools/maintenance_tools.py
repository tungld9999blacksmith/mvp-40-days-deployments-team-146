from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from src.modules.user_vehicle import errors as vehicle_errors

from . import _services

if TYPE_CHECKING:
    from .dependency import AgentToolServices


def build_maintenance_tools(services: AgentToolServices | None = None) -> list[BaseTool]:
    """Create tools bound to these service factories."""
    provider = services if services is not None else _services

    @tool
    def get_due_maintenance(config: RunnableConfig) -> dict[str, Any]:
        """Tình trạng bảo dưỡng của xe đang chọn trong phiên chat (TOOL-VEH-001).

        Tính từ dữ liệu thật của xe: số ODO mới nhất, lần bảo dưỡng định kỳ gần nhất và
        lịch bảo dưỡng của dòng xe. Không cần truyền tham số: xe lấy từ phiên chat.

        Returns:
            due_status (NORMAL / DUE_SOON / OVERDUE / UNKNOWN), due_reason (KM / TIME / BOTH), next_milestone
            (odo_milestone_km, month_milestone, due_date, items: item_code, item_name,
            is_covered_by_warranty), remaining_km, remaining_days, odometer, last_service.
            maintenance_forecast contains status, observed avg_km_per_day and estimated
            km_forecast_date/projected_due_date when consent and history allow it.
            Forecast dates do not change due_status or the observed odometer.
        """
        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                service = provider.user_vehicle_service(session)
                vehicle = service.get_owned_active_vehicle(who.user, who.user_vehicle_id)
                return service.get_maintenance_status(vehicle).model_dump(mode="json")
            except (_services.MissingCallerError, vehicle_errors.UserVehicleError) as exc:
                return _services.tool_error(exc)

    @tool
    def get_planned_trip(config: RunnableConfig) -> dict[str, Any]:
        """Đọc chuyến đi chủ xe đã khai báo và gợi ý bảo dưỡng trước ngày đi.

        Chỉ đọc xe trong phiên chat; không ghi ODO dự kiến hoặc tạo booking.
        Sở thích đặt lịch chỉ được trả khi có quyền đọc bộ nhớ và consent.
        """
        from src.modules.trip_planning.service import TripPlanningService

        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                vehicles = provider.user_vehicle_service(session)
                vehicle = vehicles.get_owned_active_vehicle(who.user, who.user_vehicle_id)
                return TripPlanningService(session, vehicles).get(vehicle).model_dump(mode="json")
            except (_services.MissingCallerError, vehicle_errors.UserVehicleError) as exc:
                return _services.tool_error(exc)

    return [get_due_maintenance, get_planned_trip]


get_due_maintenance, get_planned_trip = build_maintenance_tools()
