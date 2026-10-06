"""Tools package cho AI Agent EV Care."""

from .booking_tools import (
    find_workshops,
    get_available_slots,
    propose_booking,
)
from .cost_tools import estimate_service_cost
from .maintenance_tools import get_due_maintenance
from .RAG import (
    get_maintenance_schedule_rag,
    get_warranty_policy_rag,
    search_ev_knowledge,
)

# Danh mục công cụ cung cấp cho Agent phục vụ chủ xe (Customer Orchestrator)
CUSTOMER_AGENT_TOOLS = [
    get_due_maintenance,
    estimate_service_cost,
    find_workshops,
    get_available_slots,
    propose_booking,
    search_ev_knowledge,
]

__all__ = [
    "get_due_maintenance",
    "estimate_service_cost",
    "find_workshops",
    "get_available_slots",
    "propose_booking",
    "search_ev_knowledge",
    "get_maintenance_schedule_rag",
    "get_warranty_policy_rag",
    "CUSTOMER_AGENT_TOOLS",
]
