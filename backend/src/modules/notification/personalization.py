"""Consent lifecycle and erasure of derived snapshots, never OEM records."""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, select

from src.common.core.maintenance import Reminder
from src.common.core.notification import (
    DeliveryStatus,
    ReminderDelivery,
    ReminderPersonalizationEvent,
    ReminderPolicyEvaluation,
)
from src.common.core.notification.email import EmailOutbox, EmailVehicleGate
from src.common.core.vehicle import UserVehicle


def cancel_personalized_deliveries(db: Session, user_id: int) -> int:
    """Called inside the consent transaction. Never rewrites a retry payload."""
    vehicle_ids = db.exec(select(UserVehicle.id).where(UserVehicle.user_id == user_id).order_by(UserVehicle.id)).all()
    # The email claim uses these same gates; wait for an existing claim transaction.
    for vehicle_id in vehicle_ids:
        db.exec(
            select(EmailVehicleGate).where(EmailVehicleGate.user_vehicle_id == vehicle_id).with_for_update()
        ).first()
    rows = db.exec(
        select(ReminderDelivery, Reminder)
        .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
        .where(Reminder.user_vehicle_id.in_(vehicle_ids), ReminderDelivery.status != DeliveryStatus.SENT)
    ).all()
    cancelled = 0
    for delivery, reminder in rows:
        if not (reminder.details or {}).get("personalization"):
            continue
        delivery.status, delivery.error_code = DeliveryStatus.FAILED, "PERSONALIZATION_REVOKED"
        delivery.next_eligible_send_at = None
        db.add(delivery)
        outbox = db.get(EmailOutbox, delivery.id)
        if outbox:
            outbox.delivery_state = "cancelled"
            outbox.payload, outbox.recipient = None, None
            outbox.next_attempt_at = None
            db.add(outbox)
        cancelled += 1
    return cancelled


def erase_derived_snapshots(db: Session, user_id: int) -> int:
    db.execute(delete(ReminderPolicyEvaluation).where(ReminderPolicyEvaluation.user_id == user_id))
    vehicle_ids = select(UserVehicle.id).where(UserVehicle.user_id == user_id)
    reminders = db.exec(select(Reminder).where(Reminder.user_vehicle_id.in_(vehicle_ids))).all()
    erased = 0
    erased_ids = []
    for reminder in reminders:
        if (reminder.details or {}).get("personalization"):
            details = dict(reminder.details)
            details.pop("personalization", None)
            details.pop("triggerReasons", None)
            details["personalizationDeleted"] = True
            reminder.details = details
            db.add(reminder)
            erased += 1
            erased_ids.append(reminder.id)
    # Sent mail cannot be recalled, but our retained body must not resurface.
    delivery_ids = select(ReminderDelivery.id).where(ReminderDelivery.reminder_id.in_(erased_ids))
    for outbox in db.exec(
        select(EmailOutbox).where(EmailOutbox.user_id == user_id, EmailOutbox.delivery_id.in_(delivery_ids))
    ).all():
        if outbox.payload:
            outbox.payload, outbox.recipient = None, None
            db.add(outbox)
    return erased


def purge_derived_data(db: Session, now: datetime) -> int:
    reminders = db.exec(select(Reminder).where(Reminder.created_at < now - timedelta(days=90))).all()
    purged = 0
    for reminder in reminders:
        if (reminder.details or {}).get("personalization"):
            details = dict(reminder.details)
            details.pop("personalization", None)
            details.pop("triggerReasons", None)
            details["personalizationDeleted"] = True
            reminder.details = details
            db.add(reminder)
            purged += 1
    db.execute(
        delete(ReminderPersonalizationEvent).where(ReminderPersonalizationEvent.occurred_at < now - timedelta(days=365))
    )
    db.execute(
        delete(ReminderPolicyEvaluation).where(ReminderPolicyEvaluation.calculated_at < now - timedelta(days=90))
    )
    return purged
