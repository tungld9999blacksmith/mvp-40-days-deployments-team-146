"""Notification module - owner notification settings (API-NOTI-001..002)."""

from __future__ import annotations

from sqlmodel import Session, select

from src.common.core.identity import VehicleUser
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import UserNotificationChannel, UserNotificationSetting
from src.common.core.notification.email import EmailSuppression

from . import errors, schemas
from .domain import ALL_CHANNELS, MAX_LEAD_DAYS, MIN_LEAD_DAYS
from .email_transport import address_hash
from .preferences import channel_rows, effective_channels, load_preferences
from .recipients import has_recipient


def _to_api(channel: ReminderChannel) -> schemas.NotificationChannel:
    return schemas.NotificationChannel(channel.name)


def _to_core(channel: schemas.NotificationChannel) -> ReminderChannel:
    return ReminderChannel[channel.value]


class NotificationSettingsService:
    def __init__(
        self,
        session: Session,
        *,
        available_channels: set[ReminderChannel],
        default_lead_days: int,
        email_mode: str = "off",
    ) -> None:
        self._db = session
        self._available = available_channels
        self._default_lead_days = default_lead_days
        self._email_mode = email_mode

    def get(self, user: VehicleUser) -> schemas.NotificationSettingsOut:
        """API-NOTI-001. Read only: never creates rows."""
        prefs = load_preferences(self._db, user.user_id, default_lead_days=self._default_lead_days)
        return self._out(prefs.reminders_enabled, prefs.lead_days, prefs.channels, user)

    def update(
        self, user: VehicleUser, payload: schemas.NotificationSettingsUpdateIn
    ) -> schemas.NotificationSettingsOut:
        """API-NOTI-002. All changes are validated first and saved in one transaction."""
        if payload.reminders_enabled is None and payload.reminder_lead_days is None and not payload.channels:
            raise errors.InvalidRequestError("At least one setting must be provided.")
        if payload.reminder_lead_days is not None and not (
            MIN_LEAD_DAYS <= payload.reminder_lead_days <= MAX_LEAD_DAYS
        ):
            raise errors.InvalidLeadDaysError(MIN_LEAD_DAYS, MAX_LEAD_DAYS)

        rows = channel_rows(self._db, user.user_id)
        for change in payload.channels or []:
            channel = _to_core(change.channel)
            if change.enabled and channel not in self._available:
                raise errors.ChannelNotAvailableError(change.channel.value)
            if change.enabled and channel == ReminderChannel.EMAIL:
                if not user.email or not user.email_verified:
                    raise errors.InvalidRequestError("Email must be verified before enabling maintenance email.")
                if self._db.get(EmailSuppression, address_hash(user.email)):
                    raise errors.InvalidRequestError("This address is suppressed after a delivery problem.")
            rows[channel] = change.enabled

        setting = self._db.get(UserNotificationSetting, user.user_id)
        enabled = (
            payload.reminders_enabled
            if payload.reminders_enabled is not None
            else (setting.reminders_enabled if setting else True)
        )
        if setting is None:
            setting = UserNotificationSetting(user_id=user.user_id, reminder_lead_days=self._default_lead_days)
        setting.reminders_enabled = enabled
        if payload.reminder_lead_days is not None:
            setting.reminder_lead_days = payload.reminder_lead_days
        self._db.add(setting)

        stored = {
            row.channel: row
            for row in self._db.exec(
                select(UserNotificationChannel).where(UserNotificationChannel.user_id == user.user_id)
            ).all()
        }
        for change in payload.channels or []:
            channel = _to_core(change.channel)
            row = stored.get(channel) or UserNotificationChannel(user_id=user.user_id, channel=channel)
            row.is_enabled = change.enabled
            self._db.add(row)
        self._db.commit()

        return self._out(enabled, setting.reminder_lead_days, effective_channels(rows), user)

    # ----------------------------------------------------------- helpers
    def _out(
        self,
        reminders_enabled: bool,
        lead_days: int,
        enabled_channels: frozenset[ReminderChannel],
        user: VehicleUser,
    ) -> schemas.NotificationSettingsOut:
        suppressed = (
            bool(user.email and self._db.get(EmailSuppression, address_hash(user.email)))
            if ReminderChannel.EMAIL in self._available
            else False
        )
        verified = bool(user.email and user.email_verified)
        return schemas.NotificationSettingsOut(
            reminders_enabled=reminders_enabled,
            reminder_lead_days=lead_days,
            default_reminder_lead_days=self._default_lead_days,
            channels=[
                schemas.ChannelSettingOut(
                    channel=_to_api(channel),
                    enabled=channel in enabled_channels,
                    available=channel in self._available,
                    status=(
                        schemas.ChannelStatus.CONNECTED
                        if verified and not suppressed
                        else schemas.ChannelStatus.NOT_CONNECTED
                    )
                    if channel == ReminderChannel.EMAIL and channel in self._available
                    else self._status(user, channel),
                )
                for channel in ALL_CHANNELS
            ],
            email_recipient=user.email,
            email_verified=verified,
            email_suppressed=suppressed,
            email_transport=self._email_mode,
        )

    def _status(self, user: VehicleUser, channel: ReminderChannel) -> schemas.ChannelStatus:
        """CONNECTED = the owner has an address for the channel (verified email, phone number)."""
        if channel not in self._available:
            return schemas.ChannelStatus.COMING_SOON
        if has_recipient(user, channel):
            return schemas.ChannelStatus.CONNECTED
        return schemas.ChannelStatus.NOT_CONNECTED
