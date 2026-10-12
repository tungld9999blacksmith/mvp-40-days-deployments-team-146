"""Worker side: claim due events one by one and run their handler.

Each event goes through its own short transactions:

1. claim  — ``SELECT … FOR UPDATE SKIP LOCKED`` the oldest due row, set it
   ``processing`` with a lease (``locked_until``) and a fresh ``claim_token``,
   count the attempt, commit. Concurrent dispatchers never get the same row.
2. handle — no transaction is open while the handler runs.
3. finish — ``UPDATE … WHERE id = :id AND claim_token = :token``: ``succeeded``,
   back to ``pending`` with a backoff, or ``dead``. If the lease expired and another
   dispatcher re-claimed the row, the token no longer matches and nothing is written.

A row left ``processing`` by a crashed worker is re-claimed once its lease expires;
if it already used all attempts it becomes ``dead`` instead (poison event).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import socket
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import and_, delete, or_, update
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from .events import OutboxContext, PermanentError, RetryableError
from .models import OutboxEventRecord, OutboxStatus
from .registry import OutboxRegistry, outbox_registry

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("evcare.outbox")

SUCCEEDED, RETRIED, DEAD, LOST = "succeeded", "retried", "dead", "lost"


@dataclass(frozen=True)
class DispatcherConfig:
    batch_size: int = 50
    handler_timeout_seconds: float = 30
    lease_seconds: float = 120
    backoff_base_seconds: float = 5
    backoff_max_seconds: float = 3600

    @classmethod
    def from_settings(cls, settings) -> DispatcherConfig:
        return cls(
            batch_size=settings.outbox_batch_size,
            handler_timeout_seconds=settings.outbox_handler_timeout_seconds,
            lease_seconds=settings.outbox_lease_seconds,
            backoff_base_seconds=settings.outbox_backoff_base_seconds,
            backoff_max_seconds=settings.outbox_backoff_max_seconds,
        )


@dataclass(frozen=True)
class ClaimedEvent:
    id: UUID
    event_type: str
    schema_version: int
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    claim_token: str
    created_at: datetime
    aggregate_type: str | None
    aggregate_id: str | None
    trace_id: str | None


@dataclass
class DispatchReport:
    claimed: int = 0
    succeeded: int = 0
    retried: int = 0
    dead: int = 0
    lost: int = 0  # lease expired mid-handle; the re-claiming dispatcher owns the row

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class OutboxDispatcher:
    def __init__(
        self,
        engine: Engine,
        registry: OutboxRegistry,
        config: DispatcherConfig = DispatcherConfig(),
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        jitter: Callable[[], float] = random.random,
        worker_id: str | None = None,
    ) -> None:
        self._engine = engine
        self._registry = registry
        self._config = config
        self._clock = clock
        self._jitter = jitter
        self._worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"

    async def run_once(self) -> DispatchReport:
        """Handle up to ``batch_size`` due events, sequentially."""
        report = DispatchReport()
        for _ in range(self._config.batch_size):
            claim = self.claim_next()
            if claim is None:
                break
            report.claimed += 1
            outcome = await self.process(claim)
            setattr(report, outcome, getattr(report, outcome) + 1)
        if report.claimed:
            logger.info("outbox.dispatch", extra=report.as_dict())
        return report

    # ── claim ────────────────────────────────────────────────────────────
    def claim_next(self) -> ClaimedEvent | None:
        rec = OutboxEventRecord
        with Session(self._engine) as db:
            while True:
                now = self._clock()
                row = db.exec(
                    select(rec)
                    .where(
                        or_(
                            and_(rec.status == OutboxStatus.PENDING, rec.available_at <= now),
                            and_(rec.status == OutboxStatus.PROCESSING, rec.locked_until < now),
                        )
                    )
                    .order_by(rec.available_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                ).first()
                if row is None:
                    return None
                if row.status == OutboxStatus.PROCESSING and row.attempts >= row.max_attempts:
                    # Its last attempt never finished (worker crash / kill): stop here.
                    extra = {"event_id": str(row.id), "event_type": row.event_type, "error": "LeaseExpired"}
                    self._set_dead_fields(row, "LeaseExpired", now)
                    db.add(row)
                    db.commit()
                    logger.error("outbox.event.dead", extra=extra)
                    continue
                row.status = OutboxStatus.PROCESSING
                row.attempts += 1
                row.locked_until = now + timedelta(seconds=self._config.lease_seconds)
                row.locked_by = self._worker_id
                row.claim_token = str(uuid4())
                claim = ClaimedEvent(
                    id=row.id,
                    event_type=row.event_type,
                    schema_version=row.schema_version,
                    payload=dict(row.payload or {}),
                    attempt=row.attempts,
                    max_attempts=row.max_attempts,
                    claim_token=row.claim_token,
                    created_at=row.created_at,
                    aggregate_type=row.aggregate_type,
                    aggregate_id=row.aggregate_id,
                    trace_id=row.trace_id,
                )
                db.add(row)
                db.commit()
                return claim

    # ── handle ───────────────────────────────────────────────────────────
    async def process(self, claim: ClaimedEvent) -> str:
        handler = self._registry.get(claim.event_type)
        if handler is None:
            # Usually deploy skew: the producer runs newer code than this worker.
            return self._retry(claim, "NoHandler")
        event_cls = handler.event
        if claim.schema_version > event_cls.schema_version:
            return self._retry(claim, "SchemaVersionTooNew")
        try:
            payload = claim.payload
            if claim.schema_version < event_cls.schema_version:
                payload = event_cls.upcast(payload, claim.schema_version)
            event = event_cls.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 — a payload that cannot be read never will be
            return self._dead(claim, type(exc).__name__)

        ctx = OutboxContext(
            event_id=claim.id,
            event_type=claim.event_type,
            attempt=claim.attempt,
            max_attempts=claim.max_attempts,
            created_at=claim.created_at,
            aggregate_type=claim.aggregate_type,
            aggregate_id=claim.aggregate_id,
            trace_id=claim.trace_id,
        )
        timeout = handler.timeout_seconds or self._config.handler_timeout_seconds
        attributes = {"outbox.event_type": claim.event_type, "outbox.attempt": claim.attempt}
        if claim.trace_id:
            attributes["outbox.producer_trace_id"] = claim.trace_id
        with tracer.start_as_current_span("outbox.handle", attributes=attributes) as span:
            try:
                await asyncio.wait_for(handler.handle(event, ctx), timeout)
            except PermanentError as exc:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                return self._dead(claim, type(exc).__name__)
            except RetryableError as exc:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                return self._retry(claim, type(exc).__name__, retry_after=exc.retry_after)
            except Exception as exc:  # noqa: BLE001 — unknown failures are retried (TimeoutError included)
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                logger.warning(
                    "outbox.handler_failed",
                    extra={"event_id": str(claim.id), "event_type": claim.event_type, "attempt": claim.attempt},
                    exc_info=True,
                )
                return self._retry(claim, type(exc).__name__)
        return self._succeed(claim)

    # ── finish ───────────────────────────────────────────────────────────
    def _succeed(self, claim: ClaimedEvent) -> str:
        now = self._clock()
        done = self._finish(
            claim,
            status=OutboxStatus.SUCCEEDED,
            processed_at=now,
            last_error=None,
        )
        if not done:
            return LOST
        logger.info("outbox.event.succeeded", extra=self._log_extra(claim))
        return SUCCEEDED

    def _retry(self, claim: ClaimedEvent, error: str, *, retry_after: float | None = None) -> str:
        if claim.attempt >= claim.max_attempts:
            return self._dead(claim, error)
        delay = retry_after if retry_after is not None else self.backoff_seconds(claim.attempt)
        done = self._finish(
            claim,
            status=OutboxStatus.PENDING,
            available_at=self._clock() + timedelta(seconds=delay),
            last_error=error[:100],
        )
        if not done:
            return LOST
        logger.warning("outbox.event.retry", extra={**self._log_extra(claim), "error": error, "delay_s": delay})
        return RETRIED

    def _dead(self, claim: ClaimedEvent, error: str) -> str:
        done = self._finish(
            claim,
            status=OutboxStatus.DEAD,
            processed_at=self._clock(),
            last_error=error[:100],
        )
        if not done:
            return LOST
        logger.error("outbox.event.dead", extra={**self._log_extra(claim), "error": error})
        return DEAD

    def backoff_seconds(self, attempt: int) -> float:
        """Exponential backoff with jitter: base·2^(attempt-1), capped, then 50–100 % of it."""
        cfg = self._config
        ceiling = min(cfg.backoff_max_seconds, cfg.backoff_base_seconds * 2 ** (attempt - 1))
        return ceiling * (0.5 + self._jitter() / 2)

    def _finish(self, claim: ClaimedEvent, **values) -> bool:
        rec = OutboxEventRecord
        values |= {"locked_until": None, "locked_by": None, "claim_token": None}
        with Session(self._engine) as db:
            result = db.execute(
                update(rec)
                .where(rec.id == claim.id, rec.claim_token == claim.claim_token)
                .values(**values)
                .execution_options(synchronize_session=False)
            )
            db.commit()
        if result.rowcount != 1:
            logger.warning("outbox.lease_lost", extra=self._log_extra(claim))
            return False
        return True

    @staticmethod
    def _set_dead_fields(row: OutboxEventRecord, error: str, now: datetime) -> None:
        row.status = OutboxStatus.DEAD
        row.last_error = error
        row.processed_at = now
        row.locked_until = row.locked_by = row.claim_token = None

    @staticmethod
    def _log_extra(claim: ClaimedEvent) -> dict[str, Any]:
        return {"event_id": str(claim.id), "event_type": claim.event_type, "attempt": claim.attempt}

    # ── maintenance ──────────────────────────────────────────────────────
    def purge_succeeded(self, older_than: timedelta, *, batch: int = 1000) -> int:
        """Delete succeeded events processed before ``now - older_than``. Dead events are kept."""
        rec = OutboxEventRecord
        cutoff = self._clock() - older_than
        deleted = 0
        with Session(self._engine) as db:
            while True:
                ids = db.exec(
                    select(rec.id).where(rec.status == OutboxStatus.SUCCEEDED, rec.processed_at < cutoff).limit(batch)
                ).all()
                if not ids:
                    return deleted
                db.execute(delete(rec).where(rec.id.in_(ids)))
                db.commit()
                deleted += len(ids)

    def requeue_dead(self, event_id: UUID) -> bool:
        """Give a dead event a fresh set of attempts (after fixing its cause). False if not dead."""
        rec = OutboxEventRecord
        with Session(self._engine) as db:
            result = db.execute(
                update(rec)
                .where(rec.id == event_id, rec.status == OutboxStatus.DEAD)
                .values(status=OutboxStatus.PENDING, attempts=0, available_at=self._clock(), processed_at=None)
                .execution_options(synchronize_session=False)
            )
            db.commit()
        return result.rowcount == 1


def build_outbox_dispatcher(engine: Engine | None = None, registry: OutboxRegistry | None = None) -> OutboxDispatcher:
    from src.config import get_settings

    if engine is None:
        from src.infrastructure.supabase.db import engine as default_engine

        engine = default_engine
    return OutboxDispatcher(engine, registry or outbox_registry, DispatcherConfig.from_settings(get_settings()))
