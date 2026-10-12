"""Transactional reschedule/cancel operations for existing delivery IDs."""

from datetime import timedelta

from sqlmodel import select

from src.common.core.identity import VehicleUser
from src.common.core.maintenance import Reminder
from src.common.core.notification import DeliveryStatus, ReminderDelivery
from src.common.core.notification.email import EmailOutbox, EmailVehicleGate
from src.common.core.vehicle import UserVehicle
from src.modules.user_vehicle.domain import today_vn
from src.modules.vehicle_usage.domain import utc

from .channels import RETRYABLE_ERRORS
from .send_schedule import active, next_allowed_at

TERMINAL_CODES = {"PERSONALIZATION_REVOKED", "SCHEDULE_CANCELLED", "DELIVERY_EXPIRED", "DELIVERY_UNCERTAIN"}


def cancel_delivery(db, delivery, code="SCHEDULE_CANCELLED"):
    delivery.status, delivery.error_code = DeliveryStatus.FAILED, code
    delivery.next_eligible_send_at = None
    db.add(delivery)
    outbox = db.get(EmailOutbox, delivery.id)
    if outbox and not outbox.accepted_at:
        outbox.delivery_state = "cancelled"
        outbox.next_attempt_at = None
        db.add(outbox)


def reschedule_owner(db, user_id, prefs, now, *, timing_changed):
    vehicle_ids = db.exec(select(UserVehicle.id).where(UserVehicle.user_id == user_id).order_by(UserVehicle.id)).all()
    for vehicle_id in vehicle_ids:
        db.exec(
            select(EmailVehicleGate).where(EmailVehicleGate.user_vehicle_id == vehicle_id).with_for_update()
        ).first()
    rows = db.exec(
        select(ReminderDelivery, Reminder)
        .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
        .where(Reminder.user_vehicle_id.in_(vehicle_ids), ReminderDelivery.status != DeliveryStatus.SENT)
        .order_by(ReminderDelivery.id)
        .with_for_update(of=ReminderDelivery)
    ).all()
    for delivery, reminder in rows:
        if delivery.error_code in TERMINAL_CODES:
            continue
        if delivery.status != DeliveryStatus.PENDING and delivery.error_code not in RETRYABLE_ERRORS:
            continue
        if reminder.is_resolved or not prefs.reminders_enabled or delivery.channel not in prefs.channels:
            cancel_delivery(db, delivery)
            continue
        if not timing_changed:
            continue
        if active(prefs) and delivery.schedule_expires_at is None:
            delivery.schedule_expires_at = utc(now) + timedelta(days=7)
        if delivery.schedule_expires_at and utc(now) >= utc(delivery.schedule_expires_at):
            cancel_delivery(db, delivery, "DELIVERY_EXPIRED")
            continue
        outbox = db.get(EmailOutbox, delivery.id)
        earliest = utc(now)
        if outbox and outbox.first_attempt_at:
            # Switching from legacy timing may expand, but never indefinitely.
            if active(prefs):
                expiry = utc(outbox.first_attempt_at) + timedelta(hours=72)
                if delivery.schedule_expires_at:
                    expiry = min(expiry, utc(delivery.schedule_expires_at))
                outbox.retry_until = expiry
            if outbox.next_attempt_at:
                earliest = max(earliest, utc(outbox.next_attempt_at))
        delivery.next_eligible_send_at = next_allowed_at(earliest, prefs, initial=delivery.attempts == 0)
        if (
            outbox
            and outbox.uncertain_attempt_at
            and delivery.next_eligible_send_at >= utc(outbox.uncertain_attempt_at) + timedelta(hours=23)
        ):
            delivery.next_eligible_send_at = None
            outbox.delivery_state = "needs_reconciliation"
        if outbox:
            outbox.next_attempt_at = delivery.next_eligible_send_at
            db.add(outbox)
        db.add(delivery)


def cancel_for_booking(db, booking, now):
    """Pause matching unsent maintenance mail in the booking transaction."""
    if booking.booking_date < today_vn(now):
        return
    db.exec(select(VehicleUser).where(VehicleUser.user_id == booking.user_id).with_for_update()).one()
    db.exec(
        select(EmailVehicleGate).where(EmailVehicleGate.user_vehicle_id == booking.user_vehicle_id).with_for_update()
    ).first()
    stmt = (
        select(ReminderDelivery, Reminder)
        .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
        .where(
            Reminder.user_vehicle_id == booking.user_vehicle_id,
            ReminderDelivery.status != DeliveryStatus.SENT,
        )
    )
    if booking.odo_milestone is not None:
        stmt = stmt.where(Reminder.target_odo_milestone == booking.odo_milestone)
    for delivery, reminder in db.exec(stmt.with_for_update(of=ReminderDelivery)).all():
        cancel_delivery(db, delivery)
        reminder.is_resolved, reminder.resolution_reason = True, "HAS_BOOKING"
        db.add(reminder)
