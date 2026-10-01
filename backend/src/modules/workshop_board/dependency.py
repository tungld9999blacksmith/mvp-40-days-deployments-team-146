"""Workshop Board — dependency injection and the workshop-owner scope guard (us-037 §2).

``get_owner_workshop`` is reused by every workshop-owner API (quotes, support
tickets, progress): it resolves the single workshop of the signed-in owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, select

from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.workshop import Workshop, WorkshopStatus
from src.config import get_settings
from src.infrastructure.redis.dependency import get_redis_toolkit
from src.infrastructure.redis.toolkit import RedisToolkit
from src.infrastructure.supabase.db import get_session
from src.modules.booking.dependency import get_booking_config
from src.modules.booking.domain import BookingConfig
from src.modules.follow_up.dependency import get_follow_up_config
from src.modules.follow_up.service import FollowUpScheduler
from src.modules.notification.channels import NotificationService
from src.modules.notification.dependency import get_notification_service
from src.modules.notification.owner_notifier import OwnerNotifier
from src.modules.service_progress.dependency import get_service_progress_service
from src.modules.service_progress.service import ServiceProgressService
from src.modules.workshop_owner_onboarding.dependency import require_active_workshop_owner

from . import errors
from .service import BoardConfig, WorkshopBoardService


@dataclass(frozen=True)
class OwnerWorkshop:
    owner: WorkshopOwner
    workshop: Workshop

    def require_active(self) -> None:
        """Write endpoints need an active workshop (EDGE-812)."""
        if self.workshop.status != WorkshopStatus.ACTIVE:
            raise errors.WorkshopInactiveError()


def get_owner_workshop(
    owner: Annotated[WorkshopOwner, Depends(require_active_workshop_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerWorkshop:
    workshop = session.exec(select(Workshop).where(Workshop.owner_id == owner.id)).first()
    if workshop is None:
        raise errors.OnboardingRequiredError()
    return OwnerWorkshop(owner, workshop)


def get_board_service(
    session: Annotated[Session, Depends(get_session)],
    toolkit: Annotated[RedisToolkit, Depends(get_redis_toolkit)],
    booking_config: Annotated[BookingConfig, Depends(get_booking_config)],
    notifications: Annotated[NotificationService, Depends(get_notification_service)],
    progress: Annotated[ServiceProgressService, Depends(get_service_progress_service)],
) -> WorkshopBoardService:
    s = get_settings()
    return WorkshopBoardService(
        session,
        config=BoardConfig(
            slot_minutes=booking_config.slot_minutes,
            ws_confirm_deadline_hours=booking_config.ws_confirm_deadline_hours,
            history_days=s.board_history_days,
            max_range_days=s.board_max_range_days,
            no_show_grace_minutes=s.no_show_grace_minutes,
            block_max_days_ahead=s.slot_block_max_days_ahead,
            lock_ttl_seconds=booking_config.lock_ttl_seconds,
            frontend_url=s.frontend_url,
        ),
        locks=toolkit.locks,
        follow_ups=FollowUpScheduler(session, get_follow_up_config()),
        progress=progress,
        notifier=OwnerNotifier(session, notifications),
    )
