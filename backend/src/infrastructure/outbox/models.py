"""``outbox_event`` table: one row per domain event waiting for (or done with) its handler.

Rows are written in the producer's business transaction (``OutboxPublisher.publish``)
and moved through ``OutboxStatus`` by ``OutboxDispatcher`` in the worker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(UTC)


class OutboxStatus(StrEnum):
    PENDING = "pending"  # waiting for its first attempt or for a retry (available_at)
    PROCESSING = "processing"  # claimed by a dispatcher until locked_until
    SUCCEEDED = "succeeded"
    DEAD = "dead"  # gave up: permanent error or max_attempts reached; needs a human


class OutboxEventRecord(SQLModel, table=True):
    __tablename__ = "outbox_event"
    __table_args__ = (
        # The dispatcher scan: status + due time, oldest first.
        Index("ix_outbox_event_status_available_at", "status", "available_at"),
        Index("ix_outbox_event_aggregate", "aggregate_type", "aggregate_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    event_type: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    schema_version: int = 1
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON_TYPE, nullable=False))
    aggregate_type: str | None = Field(default=None, sa_column=Column(String(64)))
    aggregate_id: str | None = Field(default=None, sa_column=Column(String(64)))
    # Optional producer-side idempotency: a second publish with the same key is a no-op.
    dedup_key: str | None = Field(default=None, sa_column=Column(String(200), unique=True))
    status: str = Field(default=OutboxStatus.PENDING, sa_column=Column(String(16), nullable=False))
    attempts: int = 0
    max_attempts: int = 10
    available_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    locked_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    locked_by: str | None = Field(default=None, sa_column=Column(String(100)))
    claim_token: str | None = Field(default=None, sa_column=Column(String(36)))
    # Error class only: exception messages can carry PII or credentials.
    last_error: str | None = Field(default=None, sa_column=Column(String(100)))
    trace_id: str | None = Field(default=None, sa_column=Column(String(32)))
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    processed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
