from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from src.modules.cost_estimate import errors as estimate_errors

from . import _services

if TYPE_CHECKING:
    from .dependency import AgentToolServices


def build_cost_tools(services: AgentToolServices | None = None) -> list[BaseTool]:
    """Create tools bound to these service factories."""
    provider = services if services is not None else _services

    @tool
    def estimate_service_cost(
        config: RunnableConfig,
        odo_milestone: int | None = None,
        workshop_id: str | None = None,
    ) -> dict[str, Any]:
        """Ước tính chi phí một mốc bảo dưỡng của xe đang chọn tại một xưởng (TOOL-301).

        Giá lấy từ bảng giá của xưởng (price_source = WORKSHOP_PRICE) hoặc giá tham khảo
        (REFERENCE_PRICE); hạng mục được bảo hành có giá 0. Không tự bịa giá.

        Args:
            odo_milestone: Mốc km cần ước tính, lấy từ next_milestone.odo_milestone_km của
                get_due_maintenance. Bỏ trống để dùng mốc kế tiếp của xe.
            workshop_id: workshop_id (UUID) từ find_workshops. Bỏ trống để dùng xưởng ưu tiên
                của chủ xe, không có thì xưởng gần vị trí chính nhất.

        Returns:
            status (READY / NO_RULE), milestone, workshop, warranty_status, items (item_name,
            covered, price, price_source), chargeable_total, has_reference_price.
            Lỗi MILESTONE_REQUIRED / MILESTONE_NOT_FOUND kèm details.validMilestones.
        """
        try:
            workshop_uuid = UUID(workshop_id) if workshop_id else None
        except ValueError:
            return _services.tool_error(
                estimate_errors.InvalidRequestError("workshop_id must come from find_workshops.")
            )

        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                service = provider.cost_estimation_service(session)
                vehicle = service.get_owned_active_vehicle(who.user, who.user_vehicle_id)
                data = service.estimate_for_request(
                    who.user, vehicle, odo_milestone=odo_milestone, workshop_id=workshop_uuid
                )
                return data.model_dump(mode="json")
            except (_services.MissingCallerError, estimate_errors.CostEstimateError) as exc:
                return _services.tool_error(exc)

    return [estimate_service_cost]


estimate_service_cost = build_cost_tools()[0]
