"""Owner-scoped reminder detail shared by HTTP and agent tools."""

from sqlmodel import Session, select

from src.common.core.maintenance import Reminder
from src.common.core.notification import ReminderDelivery
from src.common.core.notification.email import EmailOutbox
from src.modules.oem_integration.service import utc_now
from src.modules.user_vehicle.errors import VehicleNotFoundError

from .email_service import has_milestone_booking
from .errors import NotificationError


class ReminderContextService:
    def __init__(self, db: Session, vehicles):
        self.db, self.vehicles = db, vehicles

    def get(self, user, reminder_id):
        reminder = self.db.get(Reminder, reminder_id)
        if reminder is None:
            raise NotificationError("Reminder not found.", code="REMINDER_NOT_FOUND")
        try:
            vehicle = self.vehicles.get_owned_active_vehicle(user, reminder.user_vehicle_id)
        except VehicleNotFoundError as exc:
            # Another owner's reminder must look exactly like a missing one (us-069 BR-1708).
            raise NotificationError("Reminder not found.", code="REMINDER_NOT_FOUND") from exc
        current = self.vehicles.get_maintenance_status(vehicle)
        milestone = current.next_milestone
        booked = bool(milestone and has_milestone_booking(self.db, vehicle.id, milestone.odo_milestone_km, utc_now()))
        deliveries = []
        for row in self.db.exec(select(ReminderDelivery).where(ReminderDelivery.reminder_id == reminder.id)).all():
            outbox = self.db.get(EmailOutbox, row.id)
            deliveries.append(
                {
                    "id": str(row.id),
                    "channel": row.channel.name,
                    "status": row.status.name,
                    "deliveryState": outbox.delivery_state if outbox else None,
                    "attempts": row.attempts,
                    "errorCode": row.error_code,
                    "sentAt": row.sent_at.isoformat() if row.sent_at else None,
                    "mode": outbox.mode if outbox else None,
                }
            )
        # Historical rows have no snapshot. Do not present today's numbers as old facts.
        details = reminder.details or {
            "reason": "TIME",
            "dueDate": "",
            "monthMilestone": None,
            "remainingKm": None,
            "remainingDays": None,
            "odometerKm": None,
            "odometerRecordedAt": None,
            "odometerStale": False,
            "items": [],
        }
        return {
            "reminderId": str(reminder.id),
            "userVehicleId": str(vehicle.id),
            "level": reminder.reminder_level.name,
            "odoMilestoneKm": reminder.target_odo_milestone,
            "resolved": reminder.is_resolved,
            "resolutionReason": reminder.resolution_reason,
            "details": details,
            "snapshotAvailable": reminder.details is not None,
            "currentStatus": current.model_dump(mode="json", by_alias=True),
            "hasCurrentBooking": booked,
            "deliveries": deliveries,
        }
