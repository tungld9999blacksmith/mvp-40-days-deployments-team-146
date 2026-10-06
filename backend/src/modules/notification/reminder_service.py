"""Notification module - maintenance reminder job logic (JOB-NOTI-001).

Spec: ``docs/specs/sprint-2/api/us-021-sprint-2-spec.api.md``.

``MaintenanceReminderService.remind`` handles one vehicle: it decides whether
the next milestone reached a reminder level (BR-501), records the reminder once
(BR-502), and sends every pending or retryable delivery through
``NotificationService`` (BR-505, BR-508). The due status itself comes from F3.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.common.core.identity import OnboardingStatus
from src.common.core.identity.vehicle_user import UserStatus, VehicleUser
from src.common.core.maintenance import Booking, BookingStatus, Reminder
from src.common.core.maintenance.reminder import ReminderChannel, ReminderLevel
from src.common.core.notification import DeliveryStatus, ReminderDelivery
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus, VehicleVerificationStatus
from src.modules.oem_integration.service import utc_now
from src.modules.user_vehicle.domain import DueResult, today_vn

from .channels import RETRYABLE_ERRORS, NotificationService
from .domain import build_message, decide_level
from .preferences import Preferences, load_preferences

logger = logging.getLogger(__name__)

OPEN_BOOKING_STATUSES = (
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.CHECKED_IN,
    BookingStatus.IN_PROGRESS,
)


@dataclass(frozen=True)
class ReminderOutcome:
    status: str  # "processed" | "skipped"
    reason: str | None = None
    created_level: ReminderLevel | None = None
    deliveries_sent: int = 0


class MaintenanceReminderService:
    def __init__(
        self,
        session: Session,
        notifier: NotificationService,
        calculate: Callable[[UserVehicle, datetime], DueResult],
        *,
        default_lead_days: int = 2,
        due_soon_km: int = 500,
        max_attempts: int = 3,
        app_url: str = "",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db = session
        self._notifier = notifier
        self._calculate = calculate
        self._default_lead_days = default_lead_days
        self._due_soon_km = due_soon_km
        self._max_attempts = max_attempts
        self._app_url = app_url
        self._clock = clock

    async def remind(self, user_vehicle_id: UUID) -> ReminderOutcome:
        vehicle = self._db.get(UserVehicle, user_vehicle_id)
        if (
            vehicle is None
            or vehicle.verification_status != VehicleVerificationStatus.VERIFIED
            or vehicle.link_status != VehicleLinkStatus.ACTIVE
        ):
            return ReminderOutcome("skipped", "VEHICLE_NOT_ELIGIBLE")  # BR-510
        user = self._db.get(VehicleUser, vehicle.user_id)
        if user is None or user.status != UserStatus.ACTIVE or user.onboarding_status != OnboardingStatus.ACTIVE:
            return ReminderOutcome("skipped", "USER_NOT_ACTIVE")

        prefs = load_preferences(self._db, user.user_id, default_lead_days=self._default_lead_days)
        if not prefs.reminders_enabled:
            return ReminderOutcome("skipped", "REMINDERS_DISABLED")  # AF-504

        now = self._clock()
        today = today_vn(now)
        if self._has_open_booking(vehicle.id, today):
            self._resolve_reminders(vehicle.id)  # BR-503
            return ReminderOutcome("skipped", "HAS_BOOKING")

        result = self._calculate(vehicle, now)
        milestone = result.next_milestone
        if milestone is None:
            return ReminderOutcome("skipped", "STATUS_UNKNOWN")  # EF-504

        # Reminders of an older milestone are obsolete once the milestone moved on.
        self._resolve_reminders(vehicle.id, keep_milestone=milestone.odo_milestone_km)

        level = decide_level(result, lead_days=prefs.lead_days, due_soon_km=self._due_soon_km)
        created = None
        if level is not None and self._create_reminder(vehicle.id, milestone.odo_milestone_km, level, prefs, now):
            created = level

        sent = await self._deliver_open(vehicle, user, result)
        return ReminderOutcome("processed", created_level=created, deliveries_sent=sent)

    # ---------------------------------------------------------- reminders
    def _has_open_booking(self, user_vehicle_id: UUID, today: date) -> bool:
        return (
            self._db.exec(
                select(Booking.id).where(
                    Booking.user_vehicle_id == user_vehicle_id,
                    Booking.status.in_(OPEN_BOOKING_STATUSES),
                    Booking.booking_date >= today,
                )
            ).first()
            is not None
        )

    def _resolve_reminders(self, user_vehicle_id: UUID, *, keep_milestone: int | None = None) -> None:
        stmt = select(Reminder).where(Reminder.user_vehicle_id == user_vehicle_id, Reminder.is_resolved.is_(False))
        if keep_milestone is not None:
            stmt = stmt.where(Reminder.target_odo_milestone != keep_milestone)
        reminders = self._db.exec(stmt).all()
        for reminder in reminders:
            reminder.is_resolved = True
            self._db.add(reminder)
        if reminders:
            self._db.commit()

    def _create_reminder(
        self,
        user_vehicle_id: UUID,
        milestone_km: int,
        level: ReminderLevel,
        prefs: Preferences,
        now: datetime,
    ) -> bool:
        """BR-ENT-453: insert once per (vehicle, milestone, level). False = already there."""
        exists = self._db.exec(
            select(Reminder.id).where(
                Reminder.user_vehicle_id == user_vehicle_id,
                Reminder.target_odo_milestone == milestone_km,
                Reminder.reminder_level == level,
            )
        ).first()
        if exists is not None:
            return False

        reminder = Reminder(
            user_vehicle_id=user_vehicle_id,
            target_odo_milestone=milestone_km,
            reminder_level=level,
            channel=ReminderChannel.IN_APP,  # always shown in the feed; external sends: reminder_delivery
            scheduled_at=now,
        )
        self._db.add(reminder)
        try:
            self._db.flush()
        except IntegrityError:
            # A concurrent run created it first.
            self._db.rollback()
            return False
        for channel in sorted(prefs.channels, key=lambda c: c.value):
            self._db.add(ReminderDelivery(reminder_id=reminder.id, channel=channel))
        self._db.commit()
        return True

    # --------------------------------------------------------- deliveries
    async def _deliver_open(self, vehicle: UserVehicle, user: VehicleUser, result: DueResult) -> int:
        rows = self._db.exec(
            select(ReminderDelivery, Reminder)
            .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
            .where(
                Reminder.user_vehicle_id == vehicle.id,
                Reminder.is_resolved.is_(False),
                or_(
                    ReminderDelivery.status == DeliveryStatus.PENDING,
                    and_(
                        ReminderDelivery.status == DeliveryStatus.FAILED,
                        ReminderDelivery.attempts < self._max_attempts,
                        ReminderDelivery.error_code.in_(sorted(RETRYABLE_ERRORS)),
                    ),
                ),
            )
            .order_by(Reminder.scheduled_at, ReminderDelivery.channel)
        ).all()

        sent = 0
        for delivery, reminder in rows:
            message = build_message(
                model_name=vehicle.model_name,
                license_plate=vehicle.license_plate,
                result=result,
                level=reminder.reminder_level,
                app_url=self._app_url,
            )
            outcome = await self._notifier.deliver(delivery.channel, user.user_id, message)

            delivery.attempts += 1
            delivery.last_attempt_at = self._clock()
            delivery.status = outcome.status
            delivery.error_code = outcome.error_code
            delivery.sent_at = self._clock() if outcome.status is DeliveryStatus.SENT else None
            self._db.add(delivery)

            if outcome.status is DeliveryStatus.SENT:
                sent += 1
            elif outcome.status is DeliveryStatus.FAILED:
                self._on_failure(delivery)
            self._db.commit()
        return sent

    def _on_failure(self, delivery: ReminderDelivery) -> None:
        if delivery.attempts >= self._max_attempts or delivery.error_code not in RETRYABLE_ERRORS:
            logger.error(
                "reminder delivery %s failed for good on %s (%s, attempts=%s)",
                delivery.id,
                delivery.channel.value,
                delivery.error_code,
                delivery.attempts,
            )


def list_eligible_vehicle_ids(session: Session) -> list[UUID]:
    """Vehicles the daily job visits: verified, active links of active owners (BR-510)."""
    stmt = (
        select(UserVehicle.id)
        .join(VehicleUser, VehicleUser.user_id == UserVehicle.user_id)
        .where(
            UserVehicle.verification_status == VehicleVerificationStatus.VERIFIED,
            UserVehicle.link_status == VehicleLinkStatus.ACTIVE,
            VehicleUser.status == UserStatus.ACTIVE,
            VehicleUser.onboarding_status == OnboardingStatus.ACTIVE,
        )
        .order_by(UserVehicle.id)
    )
    return list(session.exec(stmt).all())


__all__ = ["MaintenanceReminderService", "ReminderOutcome", "list_eligible_vehicle_ids"]
