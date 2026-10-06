"""Post-service follow-up — dependency injection (us-041)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.supabase.db import get_session

from .ports import FeedbackClassifier
from .service import FollowUpConfig, FollowUpService


def get_follow_up_config() -> FollowUpConfig:
    s = get_settings()
    return FollowUpConfig(
        delay_hours=s.follow_up_delay_hours,
        response_window_hours=s.follow_up_response_window_hours,
        quiet_start_hour=s.follow_up_quiet_start_hour,
        quiet_end_hour=s.follow_up_quiet_end_hour,
        frontend_url=s.app_base_url or s.frontend_url,
    )


def get_feedback_classifier() -> FeedbackClassifier | None:
    """AI-007 classifier seam. ``None`` ⇒ keyword/rating rules only (AF-904 fallback)."""
    return None


def get_follow_up_service(
    session: Annotated[Session, Depends(get_session)],
    config: Annotated[FollowUpConfig, Depends(get_follow_up_config)],
    classifier: Annotated[FeedbackClassifier | None, Depends(get_feedback_classifier)],
) -> FollowUpService:
    return FollowUpService(session, classifier=classifier, config=config)
