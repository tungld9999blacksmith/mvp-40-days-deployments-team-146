"""Notification domain: owner notification preferences and reminder delivery results."""

from .email import EmailOutbox, EmailSuppression, EmailVehicleGate, EmailWebhookEvent
from .event_delivery import (
    BookingReminder,
    BookingReminderDelivery,
    BookingReminderKind,
    BookingReminderStatus,
    FollowUpDelivery,
)
from .personalization_event import ReminderPersonalizationEvent
from .reminder_delivery import DeliveryStatus, ReminderDelivery, ReminderDeliveryRepository
from .reminder_metrics import ReminderBookingAttribution, ReminderPolicyEvaluation
from .user_notification_channel import UserNotificationChannel, UserNotificationChannelRepository
from .user_notification_setting import UserNotificationSetting, UserNotificationSettingRepository

__all__ = [
    "BookingReminder",
    "BookingReminderDelivery",
    "BookingReminderKind",
    "BookingReminderStatus",
    "FollowUpDelivery",
    "DeliveryStatus",
    "EmailOutbox",
    "EmailSuppression",
    "EmailVehicleGate",
    "EmailWebhookEvent",
    "ReminderDelivery",
    "ReminderDeliveryRepository",
    "ReminderPersonalizationEvent",
    "ReminderBookingAttribution",
    "ReminderPolicyEvaluation",
    "UserNotificationChannel",
    "UserNotificationChannelRepository",
    "UserNotificationSetting",
    "UserNotificationSettingRepository",
]
