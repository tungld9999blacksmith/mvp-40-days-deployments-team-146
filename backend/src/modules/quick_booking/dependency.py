"""Quick booking — composition root (us-061).

Builds the existing services exactly like their own HTTP endpoints do, so the
quick-booking flow and the agent tool share one implementation (BR-011, BR-1006).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.messaging import get_message_service
from src.infrastructure.redis.dependency import get_redis_toolkit
from src.infrastructure.redis.toolkit import RedisToolkit
from src.infrastructure.supabase.db import get_session
from src.modules.booking.dependency import get_booking_config, get_booking_service
from src.modules.booking.location import get_location_finder
from src.modules.conversation.dependency import get_chat_service
from src.modules.conversation.service import ChatService
from src.modules.cost_estimate.dependency import get_cost_estimation_service
from src.modules.oem_integration.dependency import get_sync_scheduler
from src.modules.user_vehicle.dependency import get_due_config, get_user_vehicle_service

from .domain import QuickBookingConfig
from .service import ChatGate, MessageSink, QuickBookingService


def get_quick_booking_config() -> QuickBookingConfig:
    s = get_settings()
    return QuickBookingConfig(
        proposal_ttl_minutes=s.quick_booking_proposal_ttl_minutes,
        min_lead_minutes=s.quick_booking_min_lead_minutes,
        horizon_days=s.quick_booking_horizon_days,
        not_due_lead_days=s.quick_booking_not_due_lead_days,
        max_lookahead_days=s.quick_booking_max_lookahead_days,
        max_workshops=s.quick_booking_max_workshops,
        ws_confirm_deadline_hours=s.booking_ws_confirm_deadline_hours,
    )


def build_quick_booking_service(
    session: Session,
    toolkit: RedisToolkit,
    *,
    chat: ChatGate | None = None,
    messages: MessageSink | None = None,
) -> QuickBookingService:
    """Without ``chat`` / ``messages`` (agent tool) only ``propose_from_agent`` is usable."""
    finder = get_location_finder()
    vehicles = get_user_vehicle_service(session, get_sync_scheduler(), get_due_config())
    return QuickBookingService(
        session,
        bookings=get_booking_service(session, toolkit, finder, get_booking_config()),
        vehicles=vehicles,
        estimates=get_cost_estimation_service(session, finder, vehicles),
        finder=finder,
        toolkit=toolkit,
        config=get_quick_booking_config(),
        chat=chat,
        messages=messages,
        lock_ttl_seconds=get_settings().booking_lock_ttl_seconds,
    )


def get_quick_booking_service(
    session: Annotated[Session, Depends(get_session)],
    chat: Annotated[ChatService, Depends(get_chat_service)],
) -> QuickBookingService:
    return build_quick_booking_service(session, get_redis_toolkit(), chat=chat, messages=get_message_service())
