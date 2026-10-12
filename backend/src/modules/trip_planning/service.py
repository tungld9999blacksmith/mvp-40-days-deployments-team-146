from datetime import timedelta
from uuid import UUID

from sqlmodel import select

from src import config as app_config
from src.common.core.identity import VehicleUser
from src.common.core.maintenance import Reminder
from src.common.core.notification import DeliveryStatus, ReminderDelivery
from src.common.core.notification.email import EmailOutbox, EmailVehicleGate
from src.common.core.vehicle import VehicleLinkStatus, VehicleTripPlan, VehicleVerificationStatus
from src.common.core.workshop import Workshop, WorkshopStatus
from src.modules.agent_memory.preferences import PreferenceService, validate_value
from src.modules.conversation.errors import ConversationError
from src.modules.notification.email_service import has_milestone_booking
from src.modules.notification.preferences import load_preferences
from src.modules.notification.scheduled_delivery import cancel_delivery
from src.modules.oem_integration.service import utc_now
from src.modules.user_vehicle.domain import today_vn
from src.modules.user_vehicle.errors import UserVehicleError
from src.modules.vehicle_usage.service import VehicleUsageService

from .domain import advise_trip
from .schemas import TripPlanEnvelope, TripPlanOut


def current_trip(db, vehicle):
    return db.exec(
        select(VehicleTripPlan)
        .where(VehicleTripPlan.user_vehicle_id == vehicle.id, VehicleTripPlan.user_id == vehicle.user_id)
        .execution_options(populate_existing=True)
    ).first()


def trip_advice(db, vehicle, result, now, forecast=None):
    trip = current_trip(db, vehicle)
    if trip is None:
        return None
    advice = advise_trip(trip, result, today=today_vn(now), forecast=forecast)
    prefs = load_preferences(
        db, vehicle.user_id, default_lead_days=app_config.get_settings().reminder_default_lead_days
    )
    advice.reminder_active = bool(
        trip.reminder_enabled
        and prefs.reminders_enabled
        and app_config.get_settings().personalized_reminders_mode_for(vehicle.user_id) == "on"
    )
    if advice.milestone_km is not None:
        advice.has_booking = has_milestone_booking(db, vehicle.id, advice.milestone_km, now)
    return advice


def trip_trigger(db, vehicle, result, now, forecast=None):
    trip = current_trip(db, vehicle)
    if not trip or not trip.reminder_enabled:
        return None
    prefs = load_preferences(
        db, vehicle.user_id, default_lead_days=app_config.get_settings().reminder_default_lead_days
    )
    if (
        not prefs.reminders_enabled
        or app_config.get_settings().personalized_reminders_mode_for(vehicle.user_id) != "on"
        or not 0 <= (trip.departure_date - today_vn(now)).days <= prefs.lead_days
    ):
        return None
    # Scheduled trip reminders use observed ODO + declared distance only.
    # Optional daily usage projection is advisory, not a second forecast trigger.
    advice = advise_trip(trip, result, today=today_vn(now))
    if advice.status != "MAINTENANCE_RECOMMENDED":
        return None
    return {
        "id": str(trip.id),
        "departureDate": trip.departure_date.isoformat(),
        "returnDate": trip.return_date.isoformat() if trip.return_date else None,
        "distanceKm": trip.distance_km,
        "projectedTripEndKm": advice.projected_trip_end_km,
        "reasons": advice.reasons,
        "usesUsageForecast": advice.projected_usage_before_departure_km > 0,
    }


class TripPlanningService:
    def __init__(self, db, vehicles, *, clock=utc_now):
        self.db, self.vehicles, self.clock = db, vehicles, clock

    def get(self, vehicle):
        trip = current_trip(self.db, vehicle)
        if trip is None:
            return TripPlanEnvelope(data=None)
        now = self.clock()
        result = self.vehicles.calculate(vehicle, now=now)
        forecast = VehicleUsageService(self.db).forecast(vehicle, result, now)
        advice = trip_advice(self.db, vehicle, result, now, forecast)
        if advice.status != "DEPARTED":
            # The existing recall guard checks consent, read flag, cohort,
            # expiration and current ownership. Preferences are suggestions only.
            for pref in PreferenceService(self.db, app_config.get_settings()).recall(vehicle.user_id, vehicle.id):
                try:
                    value = validate_value(pref["key"], pref["value"])
                except ConversationError:
                    continue
                if pref["key"] == "preferred_service_window":
                    if advice.preferred_service_window is None or pref["scope"] == "vehicle":
                        advice.preferred_service_window = value
                if pref["key"] == "preferred_workshop_id":
                    workshop = self.db.get(Workshop, UUID(value["workshop_id"]))
                    if (
                        workshop
                        and workshop.status == WorkshopStatus.ACTIVE
                        and (advice.preferred_workshop is None or pref["scope"] == "vehicle")
                    ):
                        advice.preferred_workshop = value | {"name": workshop.name}
            if advice.preferred_service_window and advice.prepare_by:
                weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                weekday = weekdays.index(advice.preferred_service_window["day"])
                suggested = today_vn(now) + timedelta(days=(weekday - today_vn(now).weekday()) % 7)
                if suggested <= advice.prepare_by:
                    advice.preferred_service_window = advice.preferred_service_window | {
                        "suggestedDate": suggested.isoformat()
                    }
        return TripPlanEnvelope(
            data=TripPlanOut(
                id=trip.id,
                departure_date=trip.departure_date,
                return_date=trip.return_date,
                distance_km=trip.distance_km,
                reminder_enabled=trip.reminder_enabled,
                updated_at=trip.updated_at,
                advice=advice,
            )
        )

    def _lock(self, vehicle):
        owner_id = vehicle.user_id
        self.db.exec(select(VehicleUser).where(VehicleUser.user_id == owner_id).with_for_update()).one()
        self.db.refresh(vehicle)
        if (
            vehicle.user_id != owner_id
            or vehicle.link_status != VehicleLinkStatus.ACTIVE
            or vehicle.verification_status != VehicleVerificationStatus.VERIFIED
        ):
            raise UserVehicleError("Vehicle is no longer available to this account.", code="VEHICLE_NOT_FOUND")
        self.db.exec(
            select(EmailVehicleGate).where(EmailVehicleGate.user_vehicle_id == vehicle.id).with_for_update()
        ).first()

    def _invalidate(self, vehicle, *, erase=False):
        # Frozen old trip facts must never be retried as a new trip. Preserve
        # accepted receipts and the milestone reminder's unique ID.
        for reminder in self.db.exec(select(Reminder).where(Reminder.user_vehicle_id == vehicle.id)).all():
            details = dict(reminder.details or {})
            if not details.get("trip"):
                continue
            for delivery in self.db.exec(
                select(ReminderDelivery).where(ReminderDelivery.reminder_id == reminder.id).with_for_update()
            ).all():
                if delivery.status != DeliveryStatus.SENT:
                    cancel_delivery(self.db, delivery)
                if erase:
                    outbox = self.db.get(EmailOutbox, delivery.id)
                    if outbox:
                        outbox.payload, outbox.recipient = None, None
                        self.db.add(outbox)
            if erase:
                details.pop("trip", None)
                details["tripDeleted"] = True
                details["triggerReasons"] = [r for r in details.get("triggerReasons", []) if not r.startswith("TRIP_")]
                reminder.details = details
            self.db.add(reminder)

    def put(self, vehicle, payload):
        now, today = self.clock(), today_vn(self.clock())
        if not today <= payload.departure_date <= today + timedelta(days=365):
            raise UserVehicleError("Departure must be within the next 365 days.", code="INVALID_TRIP_DATE")
        if payload.return_date and payload.return_date > payload.departure_date + timedelta(days=365):
            raise UserVehicleError("Trip duration must not exceed 365 days.", code="INVALID_TRIP_DATE")
        self._lock(vehicle)
        trip = self.db.exec(select(VehicleTripPlan).where(VehicleTripPlan.user_vehicle_id == vehicle.id)).first()
        if (
            trip
            and trip.user_id == vehicle.user_id
            and all(getattr(trip, key) == value for key, value in payload.model_dump().items())
        ):
            self.db.commit()
            return self.get(vehicle)
        self._invalidate(vehicle)
        if trip and trip.user_id != vehicle.user_id:
            self.db.delete(trip)
            self.db.flush()
            trip = None
        trip = trip or VehicleTripPlan(
            user_vehicle_id=vehicle.id,
            user_id=vehicle.user_id,
            departure_date=payload.departure_date,
            distance_km=payload.distance_km,
        )
        for key, value in payload.model_dump().items():
            setattr(trip, key, value)
        trip.updated_at = now
        self.db.add(trip)
        self.db.commit()
        return self.get(vehicle)

    def delete(self, vehicle):
        self._lock(vehicle)
        self._invalidate(vehicle, erase=True)
        trip = current_trip(self.db, vehicle)
        if trip:
            self.db.delete(trip)
        self.db.commit()
        return TripPlanEnvelope(data=None)
