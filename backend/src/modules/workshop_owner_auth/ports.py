"""Workshop-owner auth — ports (FEAT-AUTH-004)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class RevokeEnqueueError(Exception):
    """The revoke task could not be durably enqueued (→ 503)."""


class WorkshopSessionRevoker(Protocol):
    """Durable hand-off of a Firebase refresh-token revoke to a worker.

    Raise ``RevokeEnqueueError`` if the task was not accepted.
    """

    def enqueue_revoke(
        self, *, uid: str, owner_id: UUID | None, trace_id: str | None = None
    ) -> None: ...
