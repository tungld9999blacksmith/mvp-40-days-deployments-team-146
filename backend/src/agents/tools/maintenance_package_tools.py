"""Read-only tools for deterministic optimal maintenance packages."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from src.modules.cost_estimate import errors as estimate_errors
from src.modules.maintenance_package import MaintenancePackageService
from src.modules.user_vehicle import errors as vehicle_errors

from . import _services

if TYPE_CHECKING:
    from .dependency import AgentToolServices


def _uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise estimate_errors.WorkshopNotFoundError() from exc


def _budget(value: int | None) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise estimate_errors.InvalidRequestError("Budget must be a positive VND amount.") from exc
    if result <= 0:
        raise estimate_errors.InvalidRequestError("Budget must be a positive VND amount.")
    return result


def build_maintenance_package_tools(services: AgentToolServices | None = None) -> list[BaseTool]:
    provider = services if services is not None else _services

    @tool
    def get_service_history(config: RunnableConfig, limit: int = 5) -> dict[str, Any]:
        """Lấy lịch sử bảo dưỡng thật của xe đang chọn, mới nhất trước (Công cụ Đọc).

        Dùng sau get_due_maintenance khi chủ xe yêu cầu gợi ý gói tối ưu. Không dùng
        lịch sử để tự kết luận xe đã hoàn thành hạng mục của mốc hiện tại.

        Args:
            limit: Số bản ghi gần nhất cần trả về (1-20).
        """
        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                service = provider.user_vehicle_service(session)
                vehicle = service.get_owned_active_vehicle(who.user, who.user_vehicle_id)
                records = service.list_service_records(vehicle).items[: min(max(limit, 1), 20)]
                return {
                    "status": "READY",
                    "records": [record.model_dump(mode="json") for record in records],
                    "record_count": len(records),
                }
            except (_services.MissingCallerError, vehicle_errors.UserVehicleError) as exc:
                return _services.tool_error(exc)

    @tool
    def recommend_maintenance_packages(
        config: RunnableConfig,
        workshop_id: str | None = None,
        budget_vnd: int | None = None,
        available_minutes: int | None = None,
        priority: Literal["ESSENTIAL", "BALANCED", "COMPREHENSIVE"] = "BALANCED",
    ) -> dict[str, Any]:
        """Tạo 3 gói bảo dưỡng bằng optimizer backend từ mốc, lịch sử và giá đã xác minh.

        Công cụ chỉ dùng hạng mục MaintenanceRule của đúng mốc và giá từ
        CostEstimationService. Công cụ tự lập dự toán một lần; không gọi
        estimate_service_cost trước. Không nhận item code hoặc giá do LLM tạo.

        Args:
            workshop_id: UUID thật từ find_workshops; bỏ trống để backend chọn xưởng theo hồ sơ.
            budget_vnd: Ngân sách tối đa bằng VND, nếu chủ xe nêu.
            available_minutes: Thời gian tối đa tại xưởng, nếu chủ xe nêu.
            priority: Mức ưu tiên người dùng mong muốn.
        """
        with provider.open_session() as session:
            try:
                if available_minutes is not None and available_minutes <= 0:
                    raise estimate_errors.InvalidRequestError("Available time must be positive.")
                who = _services.caller(session, config)
                vehicle_service = provider.user_vehicle_service(session)
                vehicle = vehicle_service.get_owned_active_vehicle(who.user, who.user_vehicle_id)
                optimizer = MaintenancePackageService(
                    session,
                    vehicle_service,
                    provider.cost_estimation_service(session),
                )
                return optimizer.recommend(
                    who.user,
                    vehicle,
                    workshop_id=_uuid(workshop_id),
                    budget_vnd=_budget(budget_vnd),
                    available_minutes=available_minutes,
                    priority=priority,
                )
            except (
                _services.MissingCallerError,
                vehicle_errors.UserVehicleError,
                estimate_errors.CostEstimateError,
            ) as exc:
                return _services.tool_error(exc)

    return [get_service_history, recommend_maintenance_packages]


get_service_history, recommend_maintenance_packages = build_maintenance_package_tools()
