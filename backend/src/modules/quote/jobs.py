"""Quote background job (us-049 JOB-QT-01) — purge stale drafts (BR-1112)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session

from src.common.core.maintenance.quote import Quote, QuoteStatus

logger = logging.getLogger(__name__)


def purge_stale_drafts(session: Session, *, ttl_days: int = 7, now: datetime | None = None) -> int:
    """Hard-delete ``draft`` quotes older than ``ttl_days``; items go by ``ON DELETE CASCADE``."""
    now = now or datetime.now(UTC)
    result = session.execute(
        delete(Quote)
        .where(Quote.status == QuoteStatus.DRAFT, Quote.created_at < now - timedelta(days=ttl_days))
        .execution_options(synchronize_session=False)
    )
    session.commit()
    purged = result.rowcount or 0
    logger.info("quote.purge_stale_drafts", extra={"purged": purged})
    return purged
