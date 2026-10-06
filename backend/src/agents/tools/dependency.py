"""Composition of customer tools with explicit, replaceable service factories.

Only factories are shared across runs. Every tool opens its own session;
neither a SQLModel session nor the caller's identity is stored in this bundle.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langchain_core.tools import BaseTool
from sqlmodel import Session

from src.modules.booking.service import BookingService
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.quick_booking.service import QuickBookingService
from src.modules.user_vehicle.service import UserVehicleService

from . import _services
from .booking_tools import build_booking_tools
from .cost_tools import build_cost_tools
from .maintenance_tools import build_maintenance_tools
from .RAG.query.rag_tool import _get_rag_pipeline, build_rag_tools


@dataclass(frozen=True)
class AgentToolServices:
    open_session: Callable[[], AbstractContextManager[Session]]
    user_vehicle_service: Callable[[Session], UserVehicleService]
    cost_estimation_service: Callable[[Session], CostEstimationService]
    booking_service: Callable[[Session], BookingService]
    quick_booking_service: Callable[[Session], QuickBookingService]
    rag_pipeline: Callable[[], Any]


@lru_cache
def get_agent_tool_services() -> AgentToolServices:
    return AgentToolServices(
        open_session=_services.open_session,
        user_vehicle_service=_services.user_vehicle_service,
        cost_estimation_service=_services.cost_estimation_service,
        booking_service=_services.booking_service,
        quick_booking_service=_services.quick_booking_service,
        rag_pipeline=_get_rag_pipeline,
    )


def build_customer_agent_tools(services: AgentToolServices) -> list[BaseTool]:
    """Bind factories to tools without exposing them in the model's schema."""
    return [
        *build_maintenance_tools(services),
        *build_cost_tools(services),
        *build_booking_tools(services),
        build_rag_tools(services.rag_pipeline)[0],
    ]


@lru_cache
def get_agent_tools() -> list[BaseTool]:
    return build_customer_agent_tools(get_agent_tool_services())
