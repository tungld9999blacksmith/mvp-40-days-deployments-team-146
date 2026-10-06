"""Application-scoped read tools; identity always comes from verified context."""

from datetime import date as iso_date

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.agents.tools.result import ToolResult

from .knowledge import DemoKnowledge
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

    return [
        read_maintenance,
        estimate_service_cost,
        find_workshops,
        get_available_slots,
        propose_booking,
        search_ev_knowledge,
    ]
