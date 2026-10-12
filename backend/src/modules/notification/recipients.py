"""Notification module - where an owner can be reached on each external channel.

The adapters send to these addresses and the settings API reports a channel as
CONNECTED when one exists, so both always agree.
"""

from __future__ import annotations

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.reminder import ReminderChannel


def email_address(user: VehicleUser | None) -> str | None:
    """Only a verified email: never mail an address the owner has not proven (nor the demo account)."""
    if user is None or user.is_demo or not user.email or not user.email_verified:
        return None
    return user.email


def phone_number(user: VehicleUser | None) -> str | None:
    """The mobile number from onboarding, stored as E.164 (``+84...``); none for the demo account."""
    if user is None or user.is_demo or not user.phone:
        return None
    return user.phone


def has_recipient(user: VehicleUser | None, channel: ReminderChannel) -> bool:
    if channel is ReminderChannel.EMAIL:
        return email_address(user) is not None
    if channel is ReminderChannel.SMS:
        return phone_number(user) is not None
    return False
