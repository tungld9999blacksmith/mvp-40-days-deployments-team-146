"""Post-service follow-up — dependency injection (us-041)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.llm.dependency import get_llm_provider
from src.infrastructure.supabase.db import get_session

from .classifier import LLMFeedbackClassifier
from .ports import FeedbackClassifier
from .service import FollowUpConfig, FollowUpService

logger = logging.getLogger(__name__)


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
    if not get_settings().follow_up_llm_classifier_enabled:
        return None
    try:
        llm = get_llm_provider()
    except ValueError:  # provider misconfigured (e.g. missing key) — never block an answer
        logger.warning("follow_up.llm_classifier_unavailable", exc_info=True)
        return None
    return LLMFeedbackClassifier(llm)


def get_follow_up_service(
    session: Annotated[Session, Depends(get_session)],
    config: Annotated[FollowUpConfig, Depends(get_follow_up_config)],
    classifier: Annotated[FeedbackClassifier | None, Depends(get_feedback_classifier)],
) -> FollowUpService:
    return FollowUpService(session, classifier=classifier, config=config)
