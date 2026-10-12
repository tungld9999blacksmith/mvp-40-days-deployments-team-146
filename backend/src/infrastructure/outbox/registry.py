"""``event_type`` → handler lookup used by the dispatcher."""

from __future__ import annotations

from .events import OutboxEvent, OutboxHandler


class DuplicateHandlerError(ValueError):
    """Two handlers claimed the same ``event_type``."""


class OutboxRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, OutboxHandler] = {}

    def register(self, handler: OutboxHandler) -> OutboxHandler:
        event_cls = getattr(handler, "event", None)
        if not (isinstance(event_cls, type) and issubclass(event_cls, OutboxEvent)):
            raise TypeError(f"{type(handler).__name__}.event must be an OutboxEvent subclass")
        event_type = getattr(event_cls, "event_type", None)
        if not event_type:
            raise TypeError(f"{event_cls.__name__}.event_type is not set")
        if event_type in self._handlers:
            raise DuplicateHandlerError(f"a handler for {event_type!r} is already registered")
        self._handlers[event_type] = handler
        return handler

    def get(self, event_type: str) -> OutboxHandler | None:
        return self._handlers.get(event_type)

    def event_types(self) -> list[str]:
        return sorted(self._handlers)


# Process-wide registry. Feature modules register their handlers at import time;
# the worker imports them via OUTBOX_HANDLER_MODULES (celery/tasks/outbox_tasks.py).
outbox_registry = OutboxRegistry()


def register_handler(handler: OutboxHandler) -> OutboxHandler:
    return outbox_registry.register(handler)
