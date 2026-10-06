"""Scoped adapters implement the existing maintenance/cost contracts.

Booking deliberately exposes read methods only; confirmation stays in HTTP API.
"""

from src.agents.context import AgentCtx
from src.agents.tools.result import ToolResult

from .store import DemoError


class DemoPorts:
    def __init__(self, services):
        self.services = services

    @staticmethod
    def result(operation):
        try:
            return ToolResult(status="ok", data=operation())
        except DemoError as exc:
            return ToolResult(status="error", code=exc.code, data=exc.details, hint=str(exc))

    async def calculate_due_status(self, ctx: AgentCtx) -> ToolResult:
        return self.result(lambda: self.services.maintenance.calculate(ctx.user_id, str(ctx.vehicle_id)))

    async def estimate_service_cost(self, ctx: AgentCtx, item_codes: list[str], workshop_id=None) -> ToolResult:
        # Codes identify the active schedule; never trust a price supplied by LLM.
        if item_codes and set(item_codes) != {r["itemCode"] for r in self.services.store.rules}:
            return ToolResult(status="error", code="INVALID_ITEMS", hint="Các hạng mục không khớp mốc bảo dưỡng xe.")
        return self.result(
            lambda: self.services.cost.estimate(
                ctx.user_id, str(ctx.vehicle_id), str(workshop_id) if workshop_id else None
            )
        )

    async def find_nearby(self, ctx: AgentCtx, query=None, limit=3) -> ToolResult:
        result = self.result(lambda: self.services.booking.nearby(ctx.user_id, str(ctx.vehicle_id), query))
        if result.data:
            result.data["workshops"] = result.data["workshops"][:limit]
        return result

    async def check_availability(self, ctx: AgentCtx, workshop_id, d, time_slot=None) -> ToolResult:
        return self.result(
            lambda: self.services.booking.availability(
                ctx.user_id, str(workshop_id), d.isoformat(), time_slot.isoformat() if time_slot else None
            )
        )

    async def propose(self, ctx: AgentCtx, workshop_id, d, time_slot) -> ToolResult:
        return self.result(
            lambda: self.services.booking.proposal(
                ctx.user_id,
                str(ctx.vehicle_id),
                str(ctx.conversation_id),
                str(ctx.source_message_id),
                workshop_id,
                d,
                time_slot,
            )
        )
