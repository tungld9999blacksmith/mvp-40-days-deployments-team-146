"""Notification module - owner notification settings (API-NOTI-001..002)."""

from __future__ import annotations

from sqlmodel import Session, select

from src import config as app_config
from src.common.core.identity import VehicleUser
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import ReminderPersonalizationEvent, UserNotificationChannel, UserNotificationSetting
from src.common.core.notification.email import EmailSuppression
from src.modules.oem_integration.service import utc_now
from src.modules.vehicle_usage.service import PERSONALIZATION_POLICY_VERSION, consent_enabled

from . import errors, schemas
from .domain import ALL_CHANNELS, MAX_LEAD_DAYS, MIN_LEAD_DAYS
from .email_transport import address_hash
from .personalization import cancel_personalized_deliveries, erase_derived_snapshots
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
        clock=utc_now,
    ) -> None:
        self._db = session
        self._available = available_channels
        self._default_lead_days = default_lead_days
        self._email_mode = email_mode
        self._clock = clock

    def get(self, user: VehicleUser) -> schemas.NotificationSettingsOut:
        """API-NOTI-001. Read only: never creates rows."""
        prefs = load_preferences(self._db, user.user_id, default_lead_days=self._default_lead_days)
        return self._out(prefs.reminders_enabled, prefs.lead_days, prefs.channels, user)

    def update(
        self, user: VehicleUser, payload: schemas.NotificationSettingsUpdateIn, *, commit: bool = True
    ) -> schemas.NotificationSettingsOut:
        """API-NOTI-002. All changes are validated first and saved in one transaction."""
        if user.is_demo:
            # Shared demo account: nobody can point its reminders at their own address.
            raise errors.NotificationError("The demo account cannot be changed.", code="DEMO_READ_ONLY")
        if (
            payload.reminders_enabled is None
            and payload.reminder_lead_days is None
            and not payload.channels
            and payload.personalized_reminders_enabled is None
            and not ({"preferred_send_time", "quiet_hours", "timezone"} & payload.model_fields_set)
        ):
            raise errors.InvalidRequestError("At least one setting must be provided.")
        if payload.personalized_reminders_enabled is True:
            if payload.personalization_policy_version != PERSONALIZATION_POLICY_VERSION:
                raise errors.NotificationError(
                    "Read and accept the current personalization policy.", code="PERSONALIZATION_CONSENT_REQUIRED"
                )
            if app_config.get_settings().personalized_reminders_mode == "off":
                raise errors.NotificationError(
                    "Personalized reminders are disabled on this server.", code="PERSONALIZATION_UNAVAILABLE"
                )
        if payload.reminder_lead_days is not None and not (
            MIN_LEAD_DAYS <= payload.reminder_lead_days <= MAX_LEAD_DAYS
        ):
            raise errors.InvalidLeadDaysError(MIN_LEAD_DAYS, MAX_LEAD_DAYS)

        # Serialize concurrent updates before loading existing channels/settings.
        self._db.exec(select(VehicleUser).where(VehicleUser.user_id == user.user_id).with_for_update()).one()
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

        setting = self._db.exec(
            select(UserNotificationSetting)
            .where(UserNotificationSetting.user_id == user.user_id)
            .execution_options(populate_existing=True)
        ).first()
        enabled = (
            payload.reminders_enabled
            if payload.reminders_enabled is not None
            else (setting.reminders_enabled if setting else True)
        )
        if setting is None:
            setting = UserNotificationSetting(user_id=user.user_id, reminder_lead_days=self._default_lead_days)
        setting.reminders_enabled = enabled
        timing_fields = {"preferred_send_time", "quiet_hours", "timezone"} & payload.model_fields_set
        if "preferred_send_time" in timing_fields:
            setting.preferred_send_time = payload.preferred_send_time
        if "timezone" in timing_fields:
            setting.timezone = payload.timezone
        if "quiet_hours" in timing_fields:
            setting.quiet_hours_start = payload.quiet_hours.start if payload.quiet_hours else None
            setting.quiet_hours_end = payload.quiet_hours.end if payload.quiet_hours else None
        if payload.reminder_lead_days is not None:
            setting.reminder_lead_days = payload.reminder_lead_days
        if payload.personalized_reminders_enabled is not None:
            wanted = payload.personalized_reminders_enabled
            if not wanted:
                cancel_personalized_deliveries(self._db, user.user_id)
            if wanted != consent_enabled(setting):
                now = utc_now()
                setting.personalized_reminders_enabled = wanted
                if wanted:
                    setting.personalization_policy_version = PERSONALIZATION_POLICY_VERSION
                    setting.personalization_consent_at = now
                    setting.personalization_revoked_at = None
                else:
                    setting.personalization_revoked_at = now
                self._db.add(
                    ReminderPersonalizationEvent(
                        user_id=user.user_id,
                        action="GRANTED" if wanted else "REVOKED",
                        policy_version=PERSONALIZATION_POLICY_VERSION,
                        occurred_at=now,
                    )
                )
            setting.personalized_reminders_enabled = wanted
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
        self._db.flush()
        from .scheduled_delivery import reschedule_owner

        reschedule_owner(
            self._db,
            user.user_id,
            load_preferences(self._db, user.user_id, default_lead_days=self._default_lead_days),
            self._clock(),
            timing_changed=bool(timing_fields),
        )
        if commit:
            self._db.commit()

        return self._out(enabled, setting.reminder_lead_days, effective_channels(rows), user)

    def delete_personalization_data(self, user: VehicleUser) -> schemas.NotificationSettingsOut:
        self.update(user, schemas.NotificationSettingsUpdateIn(personalized_reminders_enabled=False), commit=False)
        erase_derived_snapshots(self._db, user.user_id)
        self._db.add(
            ReminderPersonalizationEvent(
                user_id=user.user_id,
                action="DERIVED_DATA_DELETED",
                policy_version=PERSONALIZATION_POLICY_VERSION,
                occurred_at=utc_now(),
            )
        )
        self._db.commit()
        return self.get(user)

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
        setting = self._db.get(UserNotificationSetting, user.user_id)
        cfg = app_config.get_settings()
        return schemas.NotificationSettingsOut(
            send_schedule_available=True,
            preferred_send_time=setting.preferred_send_time if setting else None,
            quiet_hours=schemas.QuietHours(start=setting.quiet_hours_start, end=setting.quiet_hours_end)
            if setting and setting.quiet_hours_start
            else None,
            timezone=setting.timezone if setting else "Asia/Ho_Chi_Minh",
            personalized_reminders_enabled=consent_enabled(setting),
            personalization_available=cfg.personalized_reminders_mode != "off",
            personalization_mode=cfg.personalized_reminders_mode_for(user.user_id),
            personalization_policy_version=PERSONALIZATION_POLICY_VERSION,
            personalization_consent_at=setting.personalization_consent_at if setting else None,
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
