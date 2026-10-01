"""Notification module - concrete channel adapters.

``LoggingDiscordAdapter`` is the only adapter for now. It resolves the owner's
private channel from ``user_discord_link`` (ENT-417) but does not call Discord:
the bot / OAuth flow is not built yet. Replace it by a bot-backed adapter that
keeps the same contract (BR-507, BR-ENT-441, BR-ENT-442).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from sqlmodel import Session

from src.common.core.identity import DiscordLinkStatus, UserDiscordLink
from src.common.core.maintenance.reminder import ReminderChannel
from src.modules.oem_integration.service import utc_now

from .channels import DeliveryResult, NotificationChannelAdapter, NotificationMessage

logger = logging.getLogger(__name__)


class LoggingDiscordAdapter(NotificationChannelAdapter):
    channel = ReminderChannel.DISCORD

    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._db = session
        self._clock = clock

    async def send(self, user_id: int, message: NotificationMessage) -> DeliveryResult:
        link = self._db.get(UserDiscordLink, user_id)
        if link is None or link.status is not DiscordLinkStatus.ACTIVE:
            return DeliveryResult.no_recipient()

        # No message body and no channel id in the log: they are personal data.
        logger.info("discord notification sent (subject=%r)", message.subject)
        link.last_delivered_at = self._clock()
        self._db.add(link)
        self._db.commit()
        return DeliveryResult.sent()
