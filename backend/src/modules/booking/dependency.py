"""Booking module — dependency injection and guards (FEAT-BOOK-001, F6)."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import OnboardingStatus, UserStatus, VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.config import get_settings
from src.infrastructure.redis.dependency import get_redis_toolkit
from src.infrastructure.redis.toolkit import RedisToolkit
from src.infrastructure.supabase.db import get_session
from src.modules.oauth.dependency import verify_firebase_token

from . import errors
from .domain import BookingConfig
from .location import WorkshopLocationFinder, get_location_finder
from .service import BookingService
from .ticket import BookingTicketService, TicketConfig


def get_booking_config() -> BookingConfig:
    s = get_settings()
    return BookingConfig(
        slot_minutes=s.slot_minutes,
        hold_minutes=s.hold_minutes,
        nearby_limit=s.booking_nearby_limit,
        search_horizon_days=s.booking_search_horizon_days,
        ws_confirm_deadline_hours=s.booking_ws_confirm_deadline_hours,
        token_ttl_seconds=s.booking_confirmation_token_ttl_seconds,
        lock_ttl_seconds=s.booking_lock_ttl_seconds,
        reschedule_min_lead_minutes=s.reschedule_min_lead_minutes,
        reschedule_max_count=s.reschedule_max_count,
    )


def get_booking_service(
    session: Annotated[Session, Depends(get_session)],
    toolkit: Annotated[RedisToolkit, Depends(get_redis_toolkit)],
    finder: Annotated[WorkshopLocationFinder, Depends(get_location_finder)],
    config: Annotated[BookingConfig, Depends(get_booking_config)],
) -> BookingService:
    return BookingService(session, toolkit, finder, config=config)


def get_ticket_service(
    session: Annotated[Session, Depends(get_session)],
    config: Annotated[BookingConfig, Depends(get_booking_config)],
) -> BookingTicketService:
    s = get_settings()
    try:
        documents = tuple(json.loads(s.booking_documents_to_bring))
    except ValueError:
        documents = ()
    return BookingTicketService(
        session,
        config=TicketConfig(
            booking=config,
            reschedule_enabled=s.feature_reschedule_enabled,
            app_base_url=s.app_base_url or s.frontend_url,
            documents_to_bring=documents,
            past_days=s.my_bookings_past_days,
        ),
    )


def require_active_vehicle_owner(
    claims: Annotated[dict, Depends(verify_firebase_token)],
    session: Annotated[Session, Depends(get_session)],
) -> VehicleUser:
    """Vehicle owner with an ACTIVE, onboarded account (BR-ENT-004)."""
    uid = claims.get("uid")
    user = session.exec(select(VehicleUser).where(VehicleUser.firebase_uid == uid)).first()
    if user is None:
        is_workshop_owner = session.exec(
            select(WorkshopOwner.id).where(WorkshopOwner.firebase_uid == uid)
        ).first()
        raise errors.ForbiddenError() if is_workshop_owner else errors.UserNotRegisteredError()
    if user.status != UserStatus.ACTIVE:
        raise errors.ForbiddenError("The account is not allowed to use this feature.")
    if user.onboarding_status != OnboardingStatus.ACTIVE:
        raise errors.OnboardingRequiredError()
    return user
