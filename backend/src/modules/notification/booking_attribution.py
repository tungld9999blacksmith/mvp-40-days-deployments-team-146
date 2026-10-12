"""Booking provenance is staged at creation and counted only after confirmation."""

from datetime import datetime, timedelta

from sqlmodel import select

from src.common.core.maintenance import Booking, BookingStatus, Reminder
from src.common.core.notification import ReminderBookingAttribution
from src.common.core.vehicle import UserVehicle
from src.modules.oem_integration.service import as_utc


def eligible_reminder(db, user_id, vehicle_id, milestone, now, reminder_id=None, *, within_window=True):
    if milestone is None:
        return None
    statement = (
        select(Reminder)
        .join(UserVehicle, UserVehicle.id == Reminder.user_vehicle_id)
        .where(
            UserVehicle.user_id == user_id,
            Reminder.user_vehicle_id == vehicle_id,
            Reminder.target_odo_milestone == milestone,
        )
    )
    if within_window:
        statement = statement.where(Reminder.scheduled_at <= now, Reminder.scheduled_at >= now - timedelta(days=7))
    if reminder_id:
        statement = statement.where(Reminder.id == reminder_id)
    return db.exec(statement.order_by(Reminder.scheduled_at.desc(), Reminder.id).limit(1)).first()


def stage_booking_origin(db, booking: Booking, now: datetime, reminder_id=None):
    reminder = eligible_reminder(db, booking.user_id, booking.user_vehicle_id, booking.odo_milestone, now, reminder_id)
    if reminder is None:
        return
    db.add(
        ReminderBookingAttribution(
            booking_id=booking.id,
            reminder_id=reminder.id,
            match_method="DIRECT" if reminder_id else "RECENT_REMINDER",
            created_at=now,
        )
    )
    db.flush()


def confirm_booking_origin(db, booking: Booking, now: datetime):
    if booking.status != BookingStatus.CONFIRMED:
        return
    attribution = db.get(ReminderBookingAttribution, booking.id)
    if attribution is None:
        # Covers legacy holds and chat bookings without explicit link metadata.
        stage_booking_origin(db, booking, as_utc(booking.created_at) if booking.created_at else now)
        attribution = db.get(ReminderBookingAttribution, booking.id)
    if attribution is None or attribution.confirmed_at is not None:
        return
    # The seven-day window applies to booking creation; workshop confirmation
    # may arrive later. Confirmation time is the metric's event time.
    if eligible_reminder(
        db,
        booking.user_id,
        booking.user_vehicle_id,
        booking.odo_milestone,
        attribution.created_at,
        attribution.reminder_id,
    ):
        attribution.confirmed_at = as_utc(now)
        db.add(attribution)
