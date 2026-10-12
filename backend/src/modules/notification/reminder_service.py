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
from datetime import datetime, timedelta
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.common.core.identity import OnboardingStatus
from src.common.core.identity.vehicle_user import UserStatus, VehicleUser
from src.common.core.maintenance import Reminder
from src.common.core.maintenance.reminder import ReminderChannel, ReminderLevel
from src.common.core.notification import DeliveryStatus, ReminderDelivery
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus, VehicleVerificationStatus
from src.modules.oem_integration.service import utc_now
from src.modules.trip_planning.service import trip_trigger
from src.modules.user_vehicle.domain import DueResult, today_vn
from src.modules.vehicle_usage.domain import utc
from src.modules.vehicle_usage.schemas import MaintenanceForecast
from src.modules.vehicle_usage.service import VehicleUsageService

from .channels import RETRYABLE_ERRORS, NotificationService
from .domain import build_message
from .email_service import has_milestone_booking
from .email_templates import build_email_message, snapshot
from .policy_service import ReminderDecision, decide_reminder
from .preferences import Preferences, load_preferences
from .scheduled_delivery import TERMINAL_CODES, cancel_delivery
from .send_schedule import active, eligible_at, next_allowed_at

logger = logging.getLogger(__name__)


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
        result = self._calculate(vehicle, now)
        milestone = result.next_milestone
        if milestone is None:
            return ReminderOutcome("skipped", "STATUS_UNKNOWN")  # EF-504

        if has_milestone_booking(self._db, vehicle.id, milestone.odo_milestone_km, now):
            self._resolve_reminders(vehicle.id, reason="HAS_BOOKING")
            return ReminderOutcome("skipped", "HAS_BOOKING")

        # Reminders of an older milestone are obsolete once the milestone moved on.
        self._resolve_reminders(vehicle.id, keep_milestone=milestone.odo_milestone_km, reason="MILESTONE_CHANGED")

        usage = VehicleUsageService(self._db)
        mode = usage.settings.personalized_reminders_mode_for(user.user_id)
        forecast_started = perf_counter()
        forecast = usage.forecast(vehicle, result, now)
        forecast_duration_ms = (perf_counter() - forecast_started) * 1000
        decision = decide_reminder(
            result,
            lead_days=prefs.lead_days,
            due_soon_km=self._due_soon_km,
            today=today_vn(now),
            forecast=forecast,
            predictive_enabled=mode == "on",
            trip=trip_trigger(self._db, vehicle, result, now),
        )
        logger.info(
            "reminder_decided mode=%s forecast=%s level=%s reasons=%s",
            mode,
            forecast.status,
            decision.level,
            decision.trigger_reasons,
        )
        if mode == "shadow":
            candidate = decide_reminder(
                result,
                lead_days=prefs.lead_days,
                due_soon_km=self._due_soon_km,
                today=today_vn(now),
                forecast=forecast,
                predictive_enabled=True,
            )
            logger.info(
                "reminder_shadow baseline_level=%s candidate_level=%s candidate_reasons=%s",
                decision.level,
                candidate.level,
                candidate.trigger_reasons,
            )
        level = decision.level
        from .metrics_service import record_policy_evaluation

        baseline = decide_reminder(
            result, lead_days=prefs.lead_days, due_soon_km=self._due_soon_km, today=today_vn(now)
        )
        candidate = decide_reminder(
            result,
            lead_days=prefs.lead_days,
            due_soon_km=self._due_soon_km,
            today=today_vn(now),
            forecast=forecast,
            predictive_enabled=True,
        )
        if prefs.personalized_reminders_enabled:
            record_policy_evaluation(
                self._db,
                vehicle,
                forecast,
                baseline,
                candidate,
                decision,
                mode=mode,
                lead_days=prefs.lead_days,
                duration_ms=forecast_duration_ms,
                now=now,
            )
        created = None
        if level is None:
            self._resolve_reminders(vehicle.id, reason="BEFORE_WINDOW")
        else:
            for old in self._db.exec(
                select(Reminder).where(
                    Reminder.user_vehicle_id == vehicle.id,
                    Reminder.target_odo_milestone == milestone.odo_milestone_km,
                    Reminder.reminder_level != level,
                    Reminder.is_resolved.is_(False),
                )
            ).all():
                old.is_resolved, old.resolution_reason = True, "SUPERSEDED"
                self._db.add(old)
            self._db.commit()
        if level is not None and self._create_reminder(
            vehicle.id, milestone.odo_milestone_km, level, prefs, now, result, decision, forecast
        ):
            created = level

        sent = await self._deliver_open(vehicle, user, result)
        return ReminderOutcome("processed", created_level=created, deliveries_sent=sent)

    async def dispatch_delivery(self, delivery_id: UUID) -> int:
        """Send one persisted delivery; never scan the fleet or create a reminder."""
        delivery = self._db.get(ReminderDelivery, delivery_id)
        reminder = self._db.get(Reminder, delivery.reminder_id) if delivery else None
        vehicle = self._db.get(UserVehicle, reminder.user_vehicle_id) if reminder else None
        user = self._db.get(VehicleUser, vehicle.user_id) if vehicle else None
        if not vehicle or not user:
            return 0
        return await self._deliver_open(vehicle, user, None, delivery_id=delivery_id)

    def _new_delivery(self, reminder_id, channel, prefs, now):
        return ReminderDelivery(
            reminder_id=reminder_id,
            channel=channel,
            next_eligible_send_at=next_allowed_at(now, prefs, initial=True),
            schedule_expires_at=utc(now) + timedelta(days=7) if active(prefs) else None,
        )

    # ---------------------------------------------------------- reminders
    def _resolve_reminders(
        self, user_vehicle_id: UUID, *, keep_milestone: int | None = None, reason: str = "STATUS_CHANGED"
    ) -> None:
        stmt = select(Reminder).where(Reminder.user_vehicle_id == user_vehicle_id, Reminder.is_resolved.is_(False))
        if keep_milestone is not None:
            stmt = stmt.where(Reminder.target_odo_milestone != keep_milestone)
        reminders = self._db.exec(stmt).all()
        for reminder in reminders:
            reminder.is_resolved = True
            reminder.resolution_reason = reason
            self._db.add(reminder)
            for delivery in self._db.exec(
                select(ReminderDelivery).where(
                    ReminderDelivery.reminder_id == reminder.id, ReminderDelivery.status != DeliveryStatus.SENT
                )
            ).all():
                cancel_delivery(self._db, delivery)
        if reminders:
            self._db.commit()

    def _create_reminder(
        self,
        user_vehicle_id: UUID,
        milestone_km: int,
        level: ReminderLevel,
        prefs: Preferences,
        now: datetime,
        result: DueResult,
        decision: ReminderDecision,
        forecast: MaintenanceForecast,
    ) -> bool:
        """BR-ENT-453: insert once per (vehicle, milestone, level). False = already there."""
        # Settings/erasure use the same owner lock. A forecast calculated before
        # revocation must never recreate an erased snapshot after that commit.
        vehicle = self._db.get(UserVehicle, user_vehicle_id)
        self._db.exec(select(VehicleUser).where(VehicleUser.user_id == vehicle.user_id).with_for_update()).one()
        prefs = load_preferences(self._db, vehicle.user_id, default_lead_days=self._default_lead_days)
        from src import config as app_config

        decision = decide_reminder(
            result,
            lead_days=prefs.lead_days,
            due_soon_km=self._due_soon_km,
            today=today_vn(now),
            forecast=forecast,
            predictive_enabled=prefs.personalized_reminders_enabled
            and app_config.get_settings().personalized_reminders_mode_for(vehicle.user_id) == "on",
            trip=trip_trigger(self._db, vehicle, result, now),
        )
        if not prefs.reminders_enabled or decision.level != level:
            self._db.commit()
            return False
        exists = self._db.exec(
            select(Reminder).where(
                Reminder.user_vehicle_id == user_vehicle_id,
                Reminder.target_odo_milestone == milestone_km,
                Reminder.reminder_level == level,
            )
        ).first()
        if exists is not None:
            if exists.is_resolved and exists.resolution_reason in {
                "HAS_BOOKING",
                "BEFORE_WINDOW",
                "STATUS_CHANGED",
                "SUPERSEDED",
            }:
                exists.is_resolved, exists.resolution_reason = False, None
                self._db.add(exists)
            existing_channels = set(
                self._db.exec(select(ReminderDelivery.channel).where(ReminderDelivery.reminder_id == exists.id)).all()
            )
            for channel in prefs.channels - existing_channels:
                self._db.add(self._new_delivery(exists.id, channel, prefs, now))
            try:
                self._db.commit()
            except IntegrityError:
                self._db.rollback()
            return False

        reminder = Reminder(
            user_vehicle_id=user_vehicle_id,
            target_odo_milestone=milestone_km,
            reminder_level=level,
            channel=ReminderChannel.IN_APP,  # always shown in the feed; external sends: reminder_delivery
            scheduled_at=now,
            details=snapshot(
                result, lead_days=prefs.lead_days, due_soon_km=self._due_soon_km, decision=decision, forecast=forecast
            ),
        )
        self._db.add(reminder)
        try:
            self._db.flush()
        except IntegrityError:
            # A concurrent run created it first.
            self._db.rollback()
            return False
        for channel in sorted(prefs.channels, key=lambda c: c.value):
            self._db.add(self._new_delivery(reminder.id, channel, prefs, now))
        self._db.commit()
        return True

    # --------------------------------------------------------- deliveries
    async def _deliver_open(
        self, vehicle: UserVehicle, user: VehicleUser, result: DueResult, *, delivery_id=None
    ) -> int:
        rows = self._db.exec(
            select(ReminderDelivery, Reminder)
            .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
            .where(
                Reminder.user_vehicle_id == vehicle.id,
                ReminderDelivery.error_code.is_(None) | ReminderDelivery.error_code.not_in(TERMINAL_CODES),
                ReminderDelivery.id == delivery_id if delivery_id else True,
                or_(
                    ReminderDelivery.status == DeliveryStatus.PENDING,
                    and_(
                        ReminderDelivery.status == DeliveryStatus.FAILED,
                        ReminderDelivery.attempts < self._max_attempts,
                        ReminderDelivery.error_code.in_(sorted(RETRYABLE_ERRORS)),
                    ),
                    and_(
                        ReminderDelivery.channel == ReminderChannel.EMAIL,
                        ReminderDelivery.status == DeliveryStatus.FAILED,
                    ),
                ),
            )
            .order_by(Reminder.scheduled_at, ReminderDelivery.channel)
        ).all()

        sent = 0
        for delivery, reminder in rows:
            now = self._clock()
            if delivery.schedule_expires_at and utc(now) >= utc(delivery.schedule_expires_at):
                cancel_delivery(self._db, delivery, "DELIVERY_EXPIRED")
                self._db.commit()
                continue
            prefs = load_preferences(self._db, user.user_id, default_lead_days=self._default_lead_days)
            if not prefs.reminders_enabled or delivery.channel not in prefs.channels:
                cancel_delivery(self._db, delivery)
                self._db.commit()
                continue
            if delivery.next_eligible_send_at and utc(delivery.next_eligible_send_at) > utc(now):
                continue
            allowed = eligible_at(now, prefs, delivery.next_eligible_send_at)
            if allowed > utc(now):
                delivery.next_eligible_send_at = allowed
                self._db.add(delivery)
                self._db.commit()
                continue
            self._db.refresh(vehicle)
            self._db.refresh(user)
            current = self._calculate(vehicle, now)
            usage = VehicleUsageService(self._db)
            mode = usage.settings.personalized_reminders_mode_for(user.user_id)
            current_forecast = usage.forecast(vehicle, current, now)
            decision = decide_reminder(
                current,
                lead_days=prefs.lead_days,
                due_soon_km=self._due_soon_km,
                today=today_vn(now),
                forecast=current_forecast,
                predictive_enabled=mode == "on",
                trip=trip_trigger(self._db, vehicle, current, now),
            )
            if (
                reminder.is_resolved
                or current.next_milestone is None
                or current.next_milestone.odo_milestone_km != reminder.target_odo_milestone
                or decision.level != reminder.reminder_level
                or has_milestone_booking(self._db, vehicle.id, reminder.target_odo_milestone, now)
                or vehicle.link_status != VehicleLinkStatus.ACTIVE
                or vehicle.verification_status != VehicleVerificationStatus.VERIFIED
                or user.status != UserStatus.ACTIVE
                or user.onboarding_status != OnboardingStatus.ACTIVE
            ):
                cancel_delivery(self._db, delivery)
                self._db.commit()
                continue
            if (reminder.details or {}).get("personalization") and (
                not prefs.personalized_reminders_enabled or mode != "on"
            ):
                cancel_delivery(self._db, delivery, "PERSONALIZATION_REVOKED")
                self._db.commit()
                continue
            if delivery.channel == ReminderChannel.EMAIL:
                from src.config import get_settings

                from .email_transport import address_hash

                cfg = get_settings()
                message = build_email_message(
                    model_name=vehicle.model_name,
                    license_plate=vehicle.license_plate,
                    milestone_km=reminder.target_odo_milestone,
                    level=reminder.reminder_level,
                    details=reminder.details
                    or snapshot(current, lead_days=prefs.lead_days, due_soon_km=self._due_soon_km),
                    app_url=cfg.email_app_url,
                    reminder_id=str(reminder.id),
                    delivery_id=str(delivery.id),
                    recipient_hash=address_hash(user.email or ""),
                    sender=cfg.email_from,
                )
                outcome = await self._notifier.deliver(delivery.channel, user.user_id, message)
                # The durable email adapter owns attempts/leases/provider results.
                if outcome.status == DeliveryStatus.SENT and not outcome.deferred:
                    sent += 1
                continue
            message = build_message(
                model_name=vehicle.model_name,
                license_plate=vehicle.license_plate,
                result=current,
                level=reminder.reminder_level,
                app_url=self._app_url,
                forecast=current_forecast if mode == "on" else None,
                trip=decision.trip,
            )
            # Cross-worker claim for non-email adapters. Email owns its gate and
            # outbox lease; every attempt releases the transaction before I/O.
            self._db.exec(select(VehicleUser).where(VehicleUser.user_id == user.user_id).with_for_update()).one()
            claimed = self._db.exec(
                select(ReminderDelivery)
                .where(ReminderDelivery.id == delivery.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).one()
            fresh_prefs = load_preferences(self._db, user.user_id, default_lead_days=self._default_lead_days)
            self._db.refresh(vehicle)
            self._db.refresh(user)
            self._db.refresh(reminder)
            if (
                claimed.status == DeliveryStatus.SENT
                or claimed.error_code in TERMINAL_CODES
                or (claimed.lease_until and utc(claimed.lease_until) > utc(now))
            ):
                self._db.commit()
                continue
            if claimed.claim_token:
                # An interrupted non-email transport has no provider idempotency
                # contract. Do not risk sending an uncertain attempt twice.
                cancel_delivery(self._db, claimed, "DELIVERY_UNCERTAIN")
                self._db.commit()
                continue
            if (
                not fresh_prefs.reminders_enabled
                or delivery.channel not in fresh_prefs.channels
                or vehicle.user_id != user.user_id
                or vehicle.link_status != VehicleLinkStatus.ACTIVE
                or vehicle.verification_status != VehicleVerificationStatus.VERIFIED
                or user.status != UserStatus.ACTIVE
                or user.onboarding_status != OnboardingStatus.ACTIVE
                or reminder.is_resolved
                or has_milestone_booking(self._db, vehicle.id, reminder.target_odo_milestone, now)
            ):
                cancel_delivery(self._db, claimed)
                self._db.commit()
                continue
            if (claimed.next_eligible_send_at and utc(claimed.next_eligible_send_at) > utc(now)) or eligible_at(
                now, fresh_prefs, claimed.next_eligible_send_at
            ) > utc(now):
                self._db.commit()
                continue
            token = str(uuid4())
            claimed.claim_token, claimed.lease_until = token, utc(now) + timedelta(seconds=60)
            claimed.attempts += 1
            claimed.last_attempt_at = now
            self._db.add(claimed)
            channel, recipient_user_id = delivery.channel, user.user_id
            self._db.commit()
            outcome = await self._notifier.deliver(channel, recipient_user_id, message)
            self._db.refresh(delivery)
            if delivery.claim_token != token:
                continue
            delivery.claim_token, delivery.lease_until = None, None
            if delivery.error_code in TERMINAL_CODES and outcome.status != DeliveryStatus.SENT:
                self._db.add(delivery)
                self._db.commit()
                continue
            delivery.status = outcome.status
            delivery.error_code = outcome.error_code
            delivery.sent_at = self._clock() if outcome.status is DeliveryStatus.SENT else None
            fresh_prefs = load_preferences(self._db, user.user_id, default_lead_days=self._default_lead_days)
            delivery.next_eligible_send_at = (
                next_allowed_at(
                    self._clock() + timedelta(minutes=5 * delivery.attempts if active(fresh_prefs) else 0), fresh_prefs
                )
                if outcome.retryable and delivery.attempts < self._max_attempts
                else None
            )
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


def list_due_delivery_ids(session: Session, now: datetime, *, max_attempts=3, limit=500) -> list[UUID]:
    """Bounded indexed queue lookup, not an ODO/fleet evaluation."""
    return list(
        session.exec(
            select(ReminderDelivery.id)
            .where(
                ReminderDelivery.next_eligible_send_at <= utc(now),
                or_(
                    ReminderDelivery.status == DeliveryStatus.PENDING,
                    and_(
                        ReminderDelivery.status == DeliveryStatus.FAILED,
                        ReminderDelivery.attempts < max_attempts,
                        ReminderDelivery.error_code.in_(RETRYABLE_ERRORS),
                    ),
                ),
            )
            .order_by(ReminderDelivery.next_eligible_send_at, ReminderDelivery.id)
            .limit(limit)
        ).all()
    )


__all__ = ["MaintenanceReminderService", "ReminderOutcome", "list_eligible_vehicle_ids"]
