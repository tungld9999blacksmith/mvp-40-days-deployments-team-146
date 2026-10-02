"""Auth module — ports (interfaces the service depends on).

The service must not know *how* the refresh-token revoke happens (Celery,
another queue, or synchronously in a test); it only needs a durable "enqueue"
operation. Concrete implementations live in ``revoker.py``.
"""

from __future__ import annotations

from typing import Protocol


class SessionRevoker(Protocol):
    """Durable hand-off of a refresh-token revoke request to a background worker.

    Must persist the task durably before returning. Raise ``RevokeEnqueueError``
    if the task could not be accepted (broker down, etc.) so the API can answer
    ``503`` per EF-104.
    """

    def enqueue_revoke(self, *, uid: str, user_id: int, trace_id: str | None = None) -> None: ...


class RevokeEnqueueError(Exception):
    """The revoke task could not be durably enqueued."""
