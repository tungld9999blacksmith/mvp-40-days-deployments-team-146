"""Best-effort event notifications to a vehicle owner (us-037 BR-810, us-041, us-057 BR-1305).

Sent after the business transaction commits, through the owner's effective
channels (us-021). A delivery problem is logged and never fails the caller.
"""

from __future__ import annotations

import logging

from sqlmodel import Session

from .channels import NotificationMessage, NotificationService
from .preferences import channel_rows, effective_channels

logger = logging.getLogger(__name__)


class OwnerNotifier:
    def __init__(self, session: Session, service: NotificationService) -> None:
        self._db = session
        self._service = service

    async def notify(self, user_id: int, message: NotificationMessage) -> int:
        """Send ``message`` on every enabled + available channel; return the number sent."""
        sent = 0
        try:
            channels = effective_channels(channel_rows(self._db, user_id))
        except Exception:  # noqa: BLE001 — never fail the caller after its commit
            logger.exception("could not load notification channels for user %s", user_id)
            return 0
        for channel in channels & self._service.available_channels():
            result = await self._service.deliver(channel, user_id, message)
            if result.status.value == "sent":
                sent += 1
            else:
                logger.warning(
                    "owner_notification.not_sent",
                    extra={"channel": channel.value, "error_code": result.error_code},
                )
        return sent
