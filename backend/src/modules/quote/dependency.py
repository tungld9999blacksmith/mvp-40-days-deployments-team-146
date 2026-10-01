"""Quote module — dependency injection (us-049)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.supabase.db import get_session
from src.modules.cost_estimate.dependency import get_cost_estimation_service
from src.modules.cost_estimate.service import CostEstimationService

from .service import QuoteConfig, QuoteService


def get_quote_service(
    session: Annotated[Session, Depends(get_session)],
    estimator: Annotated[CostEstimationService, Depends(get_cost_estimation_service)],
) -> QuoteService:
    s = get_settings()
    return QuoteService(
        session,
        estimator,
        config=QuoteConfig(
            default_validity_days=s.quote_default_validity_days,
            max_validity_days=s.quote_max_validity_days,
            draft_refresh_hours=s.quote_draft_refresh_hours,
        ),
    )
