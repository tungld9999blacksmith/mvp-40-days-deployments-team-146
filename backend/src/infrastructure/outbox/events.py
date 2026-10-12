"""Contracts shared by every outbox producer and handler.

- ``OutboxEvent`` — a pydantic model; its JSON dump is the stored payload.
- ``OutboxHandler`` — processes exactly one ``event_type``.
- ``RetryableError`` / ``PermanentError`` — how a handler steers the retry policy.

Delivery is at-least-once: a handler can see the same event twice (worker crash
after the side effect, expired lease). Handlers must be idempotent; ``ctx.event_id``
is a stable key for that.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OutboxEvent(BaseModel):
    """Base class of a domain event. Subclasses set ``event_type`` (unique, stable)."""

    model_config = ConfigDict(frozen=True)

    event_type: ClassVar[str]
    # Bump when the payload shape changes; override ``upcast`` to read older rows.
    schema_version: ClassVar[int] = 1

    @classmethod
    def upcast(cls, payload: dict[str, Any], from_version: int) -> dict[str, Any]:
        """Convert a payload stored with an older ``schema_version`` to the current shape."""
        return payload


E = TypeVar("E", bound=OutboxEvent)


@dataclass(frozen=True)
class OutboxContext:
    event_id: UUID
    event_type: str
    attempt: int  # 1 on the first attempt
    max_attempts: int
    created_at: datetime
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    trace_id: str | None = None

    @property
    def is_last_attempt(self) -> bool:
        return self.attempt >= self.max_attempts


class OutboxHandler(ABC, Generic[E]):
    """Handles one event class. Register an instance on an ``OutboxRegistry``."""

    event: ClassVar[type[OutboxEvent]]
    # None = the dispatcher default (OUTBOX_HANDLER_TIMEOUT_SECONDS).
    timeout_seconds: ClassVar[float | None] = None

    @abstractmethod
    async def handle(self, event: E, ctx: OutboxContext) -> None:
        """Do the side effect. Return = success; raise to retry (or ``PermanentError`` to stop)."""


class RetryableError(Exception):
    """Transient failure; retried with backoff. ``retry_after`` overrides the backoff (seconds)."""

    def __init__(self, message: str = "", *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentError(Exception):
    """Retrying cannot help (bad data, target deleted); the event goes straight to ``dead``."""
