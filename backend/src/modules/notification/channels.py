"""Notification module - channel abstraction (FEAT-NOTI-001 BR-506).

``NotificationService`` routes a message to the adapter registered for an
external channel. No adapter exists yet (reminders are shown in the in-app
feed only). Adding a channel means writing an adapter and registering it; the
reminder job, the rules and the API do not change.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import DeliveryStatus

logger = logging.getLogger(__name__)

# Errors worth another attempt on the next job run (BR-ENT-454).
RETRYABLE_ERRORS = frozenset({"TIMEOUT", "RATE_LIMITED", "UNAVAILABLE"})
DELIVERY_FORBIDDEN = "DELIVERY_FORBIDDEN"
NO_RECIPIENT = "NO_RECIPIENT"
CHANNEL_NOT_AVAILABLE = "CHANNEL_NOT_AVAILABLE"


@dataclass(frozen=True)
class NotificationMessage:
    """Channel-neutral content built by the backend (BR-509: nothing sensitive)."""

    subject: str
    body: str
    link: str | None = None


@dataclass(frozen=True)
class DeliveryResult:
    status: DeliveryStatus
    error_code: str | None = None

    @property
    def retryable(self) -> bool:
        return self.status is DeliveryStatus.FAILED and self.error_code in RETRYABLE_ERRORS

    @classmethod
    def sent(cls) -> DeliveryResult:
        return cls(DeliveryStatus.SENT)

    @classmethod
    def no_recipient(cls) -> DeliveryResult:
        return cls(DeliveryStatus.NO_RECIPIENT, NO_RECIPIENT)

    @classmethod
    def failed(cls, error_code: str) -> DeliveryResult:
        return cls(DeliveryStatus.FAILED, error_code)


class NotificationChannelAdapter(ABC):
    """Sends a message to one owner through one channel."""

    channel: ClassVar[ReminderChannel]

    @abstractmethod
    async def send(self, user_id: int, message: NotificationMessage) -> DeliveryResult:
        """Resolve the recipient of ``user_id`` and send.

        Must return ``DeliveryResult.no_recipient()`` when the owner has no
        usable address for this channel. Must not raise for delivery problems.
        """


class NotificationService:
    def __init__(self, adapters: Iterable[NotificationChannelAdapter] = ()) -> None:
        self._adapters: dict[ReminderChannel, NotificationChannelAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: NotificationChannelAdapter) -> None:
        self._adapters[adapter.channel] = adapter

    def available_channels(self) -> set[ReminderChannel]:
        return set(self._adapters)

    async def deliver(self, channel: ReminderChannel, user_id: int, message: NotificationMessage) -> DeliveryResult:
        adapter = self._adapters.get(channel)
        if adapter is None:
            return DeliveryResult.failed(CHANNEL_NOT_AVAILABLE)
        try:
            return await adapter.send(user_id, message)
        except Exception:  # noqa: BLE001 - one bad adapter must not stop the job
            logger.exception("notification adapter %s crashed", channel.value)
            return DeliveryResult.failed("UNAVAILABLE")
