"""Application-scoped read tools; identity always comes from verified context."""

from datetime import date as iso_date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.agents.tools.result import ToolResult

from .knowledge import DemoKnowledge
from .notifications import SettingsUpdate
from .ports import DemoPorts


def build_tools(services):
    knowledge = DemoKnowledge()
    ports = DemoPorts(services)

    def context(config):
        return config["configurable"]["ctx"]

    @tool
    async def read_maintenance(config: RunnableConfig) -> str:
        """Read verified vehicle's maintenance due status and synthetic MVP rules."""
        return (await ports.calculate_due_status(context(config))).for_llm()

    @tool
    async def estimate_service_cost(config: RunnableConfig, workshop_id: str | None = None) -> str:
        """Read server-calculated estimate, items and total. Prices are mock."""
        return (await ports.estimate_service_cost(context(config), [], workshop_id)).for_llm()

    @tool
    async def find_workshops(config: RunnableConfig) -> str:
        """List supported workshops and their IDs."""
        return (await ports.find_nearby(context(config))).for_llm()

    @tool
    async def get_available_slots(workshop_id: str, date: str, config: RunnableConfig) -> str:
        """Read available slots for exact ISO date YYYY-MM-DD; does not reserve."""
        try:
            day = iso_date.fromisoformat(date)
        except ValueError:
            return ToolResult(status="error", code="INVALID_DATE", hint="Cần ngày ISO YYYY-MM-DD.").for_llm()
        return (await ports.check_availability(context(config), workshop_id, day)).for_llm()

    @tool
    async def propose_booking(workshop_id: str, date: str, time_slot: str, config: RunnableConfig) -> str:
        """Prepare a booking proposal card for the user's chosen slot. NEVER books; owner must confirm in UI."""
        return (await ports.propose(context(config), workshop_id, date, time_slot)).for_llm()

    @tool
    def search_ev_knowledge(query: str) -> str:
        """Retrieve real warranty excerpts. If NO_EVIDENCE, explicitly say evidence is missing."""
        return ToolResult.model_validate(knowledge.search(query)).for_llm()

    def scoped(config, operation):
        ctx = context(config)

        def run():
            services.vehicles.owned(ctx.user_id, str(ctx.vehicle_id))
            return operation(ctx)

        return ports.result(run).for_llm()

    @tool
    async def get_reminder_settings(config: RunnableConfig) -> str:
        """Read email reminder preferences. Settings apply to ALL vehicles of the authenticated owner."""
        return scoped(config, lambda ctx: services.notifications.settings(ctx.user_id))

    @tool
    async def update_reminder_settings(
        config: RunnableConfig,
        reminders_enabled: bool | None = None,
        email_enabled: bool | None = None,
        reminder_lead_days: int | None = None,
    ) -> str:
        """Save explicitly requested settings (0-30 lead days) for all owned vehicles. Does NOT send email."""
        body = {}
        if reminders_enabled is not None:
            body["remindersEnabled"] = reminders_enabled
        if email_enabled is not None:
            body["channels"] = [{"channel": "EMAIL", "enabled": email_enabled}]
        if reminder_lead_days is not None:
            body["reminderLeadDays"] = reminder_lead_days
        from pydantic import ValidationError

        try:
            patch = SettingsUpdate.model_validate(body)
        except ValidationError:
            return ToolResult(
                status="error", code="INVALID_REQUEST", hint="Số ngày nhắc trước phải từ 0 đến 30."
            ).for_llm()
        return scoped(config, lambda ctx: services.notifications.update(ctx.user_id, patch))

    @tool
    async def get_reminder_context(config: RunnableConfig, reminder_id: str | None = None) -> str:
        """Read one owned reminder by ID or latest for current vehicle, including snapshot and current due status."""

        def read(ctx):
            user = services.notifications.user(ctx.user_id)
            rid = reminder_id
            if rid is None:
                records = [
                    r
                    for r in services.store.reminders.values()
                    if r["uid"] == user["uid"] and r["userVehicleId"] == str(ctx.vehicle_id)
                ]
                rid = max(records, key=lambda r: r["createdAt"])["id"] if records else ""
            result = services.notifications.context(ctx.user_id, rid)
            if result["userVehicleId"] != str(ctx.vehicle_id):
                from .store import DemoError

                raise DemoError("REMINDER_NOT_FOUND", "Lời nhắc không thuộc xe đang chọn.", 404)
            return result

        return scoped(config, read)

    return [
        read_maintenance,
        estimate_service_cost,
        find_workshops,
        get_available_slots,
        propose_booking,
        get_reminder_settings,
        update_reminder_settings,
        get_reminder_context,
        search_ev_knowledge,
    ]
