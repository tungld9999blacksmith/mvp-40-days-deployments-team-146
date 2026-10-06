"""Shared plumbing of the customer-agent tools: who is asking, and the real services.

The owner and the vehicle come from the chat session (``RunnableConfig`` →
``configurable``), never from tool arguments, so the model cannot act on
another account's vehicle (AC-009). Services are built with the same
composition functions as the HTTP endpoints (BR-011, BR-1006).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from sqlmodel import Session

from src.common.core.identity.vehicle_user import VehicleUser
from src.infrastructure.redis.dependency import get_redis_toolkit
from src.infrastructure.redis.toolkit import RedisToolkit
from src.infrastructure.supabase.db import engine
from src.modules.booking.dependency import get_booking_config, get_booking_service
from src.modules.booking.location import get_location_finder
from src.modules.booking.service import BookingService
from src.modules.cost_estimate.dependency import get_cost_estimation_service
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.oem_integration.dependency import get_sync_scheduler
from src.modules.quick_booking.service import QuickBookingService
from src.modules.user_vehicle.dependency import get_due_config, get_user_vehicle_service
from src.modules.user_vehicle.service import UserVehicleService


@dataclass(frozen=True)
class Caller:
    user: VehicleUser
    user_vehicle_id: UUID
    conversation_id: UUID | None = None


class MissingCallerError(Exception):
    code = "CHAT_CONTEXT_MISSING"
    message = "The tool needs the owner and the vehicle of the chat session."


@contextmanager
def open_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def redis_toolkit() -> RedisToolkit:
    return get_redis_toolkit()


def caller(session: Session, config: RunnableConfig | None) -> Caller:
    configurable = (config or {}).get("configurable") or {}
    try:
        user_id = int(configurable["user_id"])
        user_vehicle_id = UUID(str(configurable["user_vehicle_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise MissingCallerError() from exc
    user = session.get(VehicleUser, user_id)
    if user is None:
        raise MissingCallerError()
    try:
        conversation_id = UUID(str(configurable["conversation_id"])) if configurable.get("conversation_id") else None
    except ValueError:
        conversation_id = None
    return Caller(user, user_vehicle_id, conversation_id)


def user_vehicle_service(session: Session) -> UserVehicleService:
    return get_user_vehicle_service(session, get_sync_scheduler(), get_due_config())


def cost_estimation_service(session: Session) -> CostEstimationService:
    return get_cost_estimation_service(session, get_location_finder(), user_vehicle_service(session))


def booking_service(session: Session) -> BookingService:
    return get_booking_service(session, redis_toolkit(), get_location_finder(), get_booking_config())


def quick_booking_service(session: Session) -> QuickBookingService:
    # The HTTP composition root also depends on ChatService. Import it only
    # when a proposal is requested, after the agent dependencies are composed.
    from src.modules.quick_booking.dependency import build_quick_booking_service

    return build_quick_booking_service(session, redis_toolkit())


def tool_error(exc: Exception) -> dict[str, Any]:
    """Domain error → a result the model can read and explain (never a stack trace)."""
    out: dict[str, Any] = {
        "status": "ERROR",
        "error_code": getattr(exc, "code", type(exc).__name__),
        "message": getattr(exc, "message", str(exc)),
    }
    details = getattr(exc, "details", None)
    if details:
        out["details"] = details
    return out
