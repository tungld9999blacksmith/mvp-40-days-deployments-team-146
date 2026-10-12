"""Main maintenance email: durable claims, frozen retries, webhook receipts.

Never sends booking/follow-up mail. DB transactions finish BEFORE HTTP.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import OnboardingStatus, UserStatus, VehicleUser
from src.common.core.maintenance import Booking, BookingStatus, Reminder
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import DeliveryStatus, ReminderDelivery
from src.common.core.notification.email import EmailOutbox, EmailSuppression, EmailVehicleGate, EmailWebhookEvent
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus, VehicleVerificationStatus
from src.config import Settings
from src.modules.oem_integration.service import as_utc, utc_now
from src.modules.user_vehicle.domain import today_vn

from .channels import DeliveryResult, NotificationChannelAdapter, NotificationMessage
from .email_transport import ResendEmailTransport, address_hash
from .preferences import load_preferences
from .scheduled_delivery import TERMINAL_CODES, cancel_delivery
from .send_schedule import active, eligible_at, next_allowed_at

BLOCKING_STATES = {"bounced", "complained", "suppressed"}
STATE_RANK = {
    "pending": 0,
    "accepted": 1,
    "delayed": 2,
    "delivered": 3,
    "failed": 4,
    "bounced": 5,
    "suppressed": 6,
    "complained": 7,
}
EVENT_STATES = {f"email.{name}": name for name in ("delivered", "bounced", "complained", "suppressed", "failed")}
EVENT_STATES.update({"email.sent": "accepted", "email.delivery_delayed": "delayed"})


def has_milestone_booking(db: Session, vehicle_id: UUID, milestone: int, now: datetime) -> bool:
    # NULL means a legacy booking without enough information: conservatively pause.
    return (
        db.exec(
            select(Booking.id).where(
                Booking.user_vehicle_id == vehicle_id,
                Booking.status.in_(
                    [
                        BookingStatus.PENDING,
                        BookingStatus.CONFIRMED,
                        BookingStatus.CHECKED_IN,
                        BookingStatus.IN_PROGRESS,
                    ]
                ),
                or_(
                    Booking.booking_date >= today_vn(now),
                    Booking.status.in_([BookingStatus.CHECKED_IN, BookingStatus.IN_PROGRESS]),
                ),
                or_(Booking.odo_milestone == milestone, Booking.odo_milestone.is_(None)),
            )
        ).first()
        is not None
    )


def email_configuration_ready(cfg: Settings) -> bool:
    if cfg.email_mode == "off":
        return False
    if cfg.email_mode == "mock":
        return True
    if cfg.firebase_auth_emulator_host or cfg.demo_now:
        return False
    return bool(cfg.resend_api_key.strip() and cfg.email_from.strip() and cfg.resend_webhook_secret.strip())


class MaintenanceEmailAdapter(NotificationChannelAdapter):
    channel = ReminderChannel.EMAIL

    def __init__(self, db: Session, cfg: Settings, *, transport=None, clock=utc_now):
        self.db, self.cfg, self.clock = db, cfg, clock
        self.transport = transport or ResendEmailTransport(cfg.resend_api_key)

    def _defer(self, code: str) -> DeliveryResult:
        # A deferred eligibility/lease check does not count as a provider attempt.
        self.db.commit()
        return DeliveryResult(DeliveryStatus.PENDING, code, deferred=True)

    def _eligible(self, user: VehicleUser, vehicle: UserVehicle, reminder: Reminder, now: datetime) -> str | None:
        if user.status != UserStatus.ACTIVE or user.onboarding_status != OnboardingStatus.ACTIVE:
            return "USER_NOT_ACTIVE"
        if user.is_demo:
            # The shared demo account never mails anyone (modules/demo_account).
            return "DEMO_ACCOUNT"
        if (
            vehicle.user_id != user.user_id
            or vehicle.link_status != VehicleLinkStatus.ACTIVE
            or vehicle.verification_status != VehicleVerificationStatus.VERIFIED
        ):
            return "VEHICLE_NOT_ELIGIBLE"
        prefs = load_preferences(self.db, user.user_id, default_lead_days=self.cfg.reminder_default_lead_days)
        if not prefs.reminders_enabled or ReminderChannel.EMAIL not in prefs.channels:
            return "EMAIL_OPT_OUT"
        if not user.email or not user.email_verified:
            return "EMAIL_NOT_VERIFIED"
        if self.db.get(EmailSuppression, address_hash(user.email)):
            return "EMAIL_SUPPRESSED"
        if reminder.is_resolved or has_milestone_booking(self.db, vehicle.id, reminder.target_odo_milestone, now):
            return "REMINDER_CLOSED"
        from src.modules.trip_planning.service import trip_trigger
        from src.modules.user_vehicle.dependency import get_due_config
        from src.modules.user_vehicle.service import UserVehicleService
        from src.modules.vehicle_usage.service import VehicleUsageService

        from .policy_service import decide_reminder

        result = UserVehicleService(self.db, _NoopScheduler(), config=get_due_config(), clock=lambda: now).calculate(
            vehicle, now=now
        )
        if result.next_milestone is None or result.next_milestone.odo_milestone_km != reminder.target_odo_milestone:
            return "MILESTONE_CHANGED"
        if (reminder.details or {}).get("personalization") and (
            not prefs.personalized_reminders_enabled or self.cfg.personalized_reminders_mode_for(user.user_id) != "on"
        ):
            return "PERSONALIZATION_REVOKED"
        forecast = VehicleUsageService(self.db, self.cfg).forecast(vehicle, result, now)
        current_level = decide_reminder(
            result,
            lead_days=prefs.lead_days,
            due_soon_km=self.cfg.due_soon_km,
            today=today_vn(now),
            forecast=forecast,
            predictive_enabled=self.cfg.personalized_reminders_mode_for(user.user_id) == "on",
            trip=trip_trigger(self.db, vehicle, result, now),
        ).level
        if current_level != reminder.reminder_level:
            return "STATUS_CHANGED"
        return None

    async def send(self, user_id: int, message: NotificationMessage) -> DeliveryResult:
        if message.kind != "MAINTENANCE_REMINDER" or not message.delivery_id:
            return DeliveryResult.failed("EMAIL_MAINTENANCE_ONLY")
        if not email_configuration_ready(self.cfg):
            return self._defer("EMAIL_NOT_CONFIGURED")
        try:
            delivery_id = UUID(message.delivery_id)
        except ValueError:
            return DeliveryResult.failed("INVALID_DELIVERY")
        delivery = self.db.get(ReminderDelivery, delivery_id)
        reminder = self.db.get(Reminder, delivery.reminder_id) if delivery else None
        vehicle = self.db.get(UserVehicle, reminder.user_vehicle_id) if reminder else None
        user = self.db.get(VehicleUser, user_id)
        if not delivery or delivery.channel != ReminderChannel.EMAIL or not reminder or not vehicle or not user:
            return self._defer("INVALID_DELIVERY")
        if delivery.error_code in TERMINAL_CODES:
            return self._defer(delivery.error_code)
        now = self.clock()
        # Serialize all maintenance email claims for the same vehicle.
        if self.db.get(EmailVehicleGate, vehicle.id) is None:
            try:
                self.db.add(EmailVehicleGate(user_vehicle_id=vehicle.id))
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
        self.db.exec(
            select(EmailVehicleGate).where(EmailVehicleGate.user_vehicle_id == vehicle.id).with_for_update()
        ).one()
        # Reload cached objects after acquiring the cross-worker lock.
        self.db.refresh(delivery)
        self.db.refresh(reminder)
        self.db.refresh(user)
        self.db.refresh(vehicle)
        if delivery.error_code in TERMINAL_CODES:
            return self._defer(delivery.error_code)
        outbox = self.db.get(EmailOutbox, delivery_id)
        if delivery.status == DeliveryStatus.SENT:
            self.db.commit()
            return DeliveryResult.sent(outbox.provider_message_id if outbox else None)
        reason = self._eligible(user, vehicle, reminder, now)
        if reason:
            cancel_delivery(
                self.db,
                delivery,
                "PERSONALIZATION_REVOKED" if reason == "PERSONALIZATION_REVOKED" else "SCHEDULE_CANCELLED",
            )
            return self._defer(reason)
        prefs = load_preferences(self.db, user_id, default_lead_days=self.cfg.reminder_default_lead_days)
        if delivery.schedule_expires_at and as_utc(now) >= as_utc(delivery.schedule_expires_at):
            cancel_delivery(self.db, delivery, "DELIVERY_EXPIRED")
            return self._defer("DELIVERY_EXPIRED")
        if delivery.next_eligible_send_at and as_utc(now) < as_utc(delivery.next_eligible_send_at):
            return self._defer("SEND_TIME_NOT_REACHED")
        allowed = eligible_at(now, prefs, delivery.next_eligible_send_at)
        if allowed > as_utc(now):
            delivery.next_eligible_send_at = allowed
            self.db.add(delivery)
            return self._defer("QUIET_HOURS")
        if outbox:
            # Resend's key retention is 24h. Ambiguous outcomes/crashes must not
            # be retried outside a conservative 23h window, even when the owner
            # schedule gives a longer logical retry deadline.
            if outbox.uncertain_attempt_at and as_utc(now) >= as_utc(outbox.uncertain_attempt_at) + timedelta(hours=23):
                outbox.delivery_state = "needs_reconciliation"
                outbox.next_attempt_at = None
                delivery.next_eligible_send_at = None
                self.db.add(outbox)
                self.db.add(delivery)
                return self._defer("EMAIL_RECONCILE_REQUIRED")
            if outbox.mode != self.cfg.email_mode:
                return self._defer("EMAIL_MODE_CHANGED")
            if outbox.recipient_hash != address_hash(user.email):
                return self._defer("EMAIL_RECIPIENT_CHANGED")
            if outbox.delivery_state in BLOCKING_STATES | {"failed", "needs_reconciliation", "cancelled"}:
                delivery.next_eligible_send_at = None
                self.db.add(delivery)
                return self._defer("EMAIL_TERMINAL")
            if outbox.lease_until and as_utc(outbox.lease_until) > now:
                return self._defer("EMAIL_CLAIMED")
            if outbox.next_attempt_at and as_utc(outbox.next_attempt_at) > now:
                return self._defer("EMAIL_BACKOFF")
            if delivery.attempts >= self.cfg.reminder_max_attempts or (
                outbox.retry_until and now >= as_utc(outbox.retry_until)
            ):
                outbox.delivery_state = "needs_reconciliation"
                self.db.add(outbox)
                delivery.next_eligible_send_at = None
                self.db.add(delivery)
                return self._defer("EMAIL_RECONCILE_REQUIRED")
            if not outbox.payload or not outbox.recipient:
                return self._defer("EMAIL_PAYLOAD_EXPIRED")
        else:
            # Real and mock cooldowns are separate; uncertain attempts block new IDs.
            peers = self.db.exec(
                select(EmailOutbox).where(
                    EmailOutbox.user_vehicle_id == vehicle.id,
                    EmailOutbox.mode == self.cfg.email_mode,
                    EmailOutbox.delivery_id != delivery_id,
                )
            ).all()
            for peer in peers:
                if peer.accepted_at and as_utc(peer.accepted_at) > now - timedelta(days=7):
                    delivery.next_eligible_send_at = next_allowed_at(
                        as_utc(peer.accepted_at) + timedelta(days=7), prefs
                    )
                    self.db.add(delivery)
                    return self._defer("EMAIL_COOLDOWN")
                if peer.delivery_state == "needs_reconciliation" or (
                    peer.first_attempt_at
                    and peer.delivery_state not in BLOCKING_STATES | {"failed", "delivered", "accepted", "cancelled"}
                ):
                    return self._defer("EMAIL_UNCERTAIN_PREVIOUS_DELIVERY")
            outbox = EmailOutbox(
                delivery_id=delivery_id,
                user_id=user_id,
                user_vehicle_id=vehicle.id,
                mode=self.cfg.email_mode,
                recipient_hash=address_hash(user.email),
                recipient=user.email,
                payload=asdict(message),
                created_at=now,
                first_attempt_at=now,
                retry_until=min(
                    now + timedelta(hours=72 if active(prefs) else 23), as_utc(delivery.schedule_expires_at)
                )
                if delivery.schedule_expires_at
                else now + timedelta(hours=72 if active(prefs) else 23),
            )
        token = str(uuid4())
        previous_uncertainty = outbox.uncertain_attempt_at
        outbox.uncertain_attempt_at = outbox.uncertain_attempt_at or now
        outbox.claim_token, outbox.lease_until = token, now + timedelta(seconds=60)
        outbox.next_attempt_at = None
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.next_eligible_send_at = outbox.lease_until
        frozen_recipient = outbox.recipient
        frozen_message = NotificationMessage(**outbox.payload)
        self.db.add(outbox)
        self.db.add(delivery)
        self.db.commit()  # No DB transaction is held over provider I/O.
        try:
            outcome = (
                DeliveryResult.sent(f"mock-{delivery_id}")
                if self.cfg.email_mode == "mock"
                else await self.transport.send(frozen_recipient, frozen_message)
            )
        except Exception:
            outcome = DeliveryResult.failed("UNAVAILABLE")
        # The claim token prevents a stale worker from overwriting a newer result.
        self.db.expire_all()
        outbox = self.db.exec(select(EmailOutbox).where(EmailOutbox.delivery_id == delivery_id).with_for_update()).one()
        delivery = self.db.get(ReminderDelivery, delivery_id)
        if outbox.claim_token != token:
            return self._defer("EMAIL_CLAIM_LOST")
        outbox.claim_token, outbox.lease_until = None, None
        delivery.next_eligible_send_at = None
        if outcome.status == DeliveryStatus.SENT:
            outbox.uncertain_attempt_at = None
            outbox.provider_message_id = outcome.provider_message_id
            outbox.accepted_at = outbox.accepted_at or self.clock()
            if STATE_RANK.get(outbox.delivery_state, 0) < STATE_RANK["accepted"]:
                outbox.delivery_state = "accepted"
            delivery.status, delivery.sent_at, delivery.error_code = DeliveryStatus.SENT, outbox.accepted_at, None
            self.db.add(outbox)
            self._reconcile(outbox)
        else:
            # A verified early webhook can prove acceptance after an HTTP timeout.
            if outbox.accepted_at:
                delivery.status, delivery.sent_at = DeliveryStatus.SENT, outbox.accepted_at
                delivery.error_code = None
            elif delivery.error_code not in TERMINAL_CODES:
                if outcome.error_code == "RATE_LIMITED":
                    outbox.uncertain_attempt_at = previous_uncertainty
                delivery.status, delivery.error_code = outcome.status, outcome.error_code
                if outcome.retryable:
                    if delivery.attempts < self.cfg.reminder_max_attempts:
                        current_prefs = load_preferences(
                            self.db, user_id, default_lead_days=self.cfg.reminder_default_lead_days
                        )
                        outbox.next_attempt_at = next_allowed_at(
                            self.clock() + timedelta(minutes=5 * delivery.attempts), current_prefs
                        )
                        if outbox.retry_until and as_utc(outbox.next_attempt_at) >= as_utc(outbox.retry_until):
                            outbox.delivery_state = "needs_reconciliation"
                            outbox.next_attempt_at = None
                        if (
                            outbox.next_attempt_at
                            and outbox.uncertain_attempt_at
                            and as_utc(outbox.next_attempt_at)
                            >= as_utc(outbox.uncertain_attempt_at) + timedelta(hours=23)
                        ):
                            outbox.delivery_state = "needs_reconciliation"
                            outbox.next_attempt_at = None
                        delivery.next_eligible_send_at = outbox.next_attempt_at
                    else:
                        outbox.delivery_state = "needs_reconciliation"
                else:
                    outbox.delivery_state = "failed"
        self.db.add(outbox)
        self.db.add(delivery)
        self.db.commit()
        return DeliveryResult(delivery.status, delivery.error_code, outbox.provider_message_id)

    def _apply(self, outbox: EmailOutbox, event: EmailWebhookEvent):
        if outbox.mode != "resend" or (
            outbox.provider_message_id and outbox.provider_message_id != event.provider_message_id
        ):
            return
        if event.recipient_hash and event.recipient_hash != outbox.recipient_hash:
            return
        state = EVENT_STATES.get(event.event_type)
        if state:
            outbox.provider_message_id = event.provider_message_id
            outbox.accepted_at = outbox.accepted_at or event.received_at
            if STATE_RANK.get(state, 0) > STATE_RANK.get(outbox.delivery_state, 0):
                outbox.delivery_state = state
            if state in BLOCKING_STATES:
                self._suppress(outbox.recipient_hash, state)
            delivery = self.db.get(ReminderDelivery, outbox.delivery_id)
            delivery.status, delivery.sent_at, delivery.error_code = DeliveryStatus.SENT, outbox.accepted_at, None
            self.db.add(delivery)
        event.applied_at = self.clock()
        self.db.add(event)
        self.db.add(outbox)

    def _suppress(self, recipient_hash: str, state: str):
        if not self.db.get(EmailSuppression, recipient_hash):
            # Savepoint tolerates simultaneous bounce/complaint for the same address.
            try:
                with self.db.begin_nested():
                    self.db.add(EmailSuppression(recipient_hash=recipient_hash, reason=state, created_at=self.clock()))
                    self.db.flush()
            except IntegrityError:
                pass

    def _reconcile(self, outbox: EmailOutbox):
        events = self.db.exec(
            select(EmailWebhookEvent).where(
                EmailWebhookEvent.applied_at.is_(None),
                or_(
                    EmailWebhookEvent.provider_message_id == outbox.provider_message_id,
                    EmailWebhookEvent.delivery_id == outbox.delivery_id,
                ),
            )
        ).all()
        for event in events:
            self._apply(outbox, event)

    def record_webhook(self, event_id: str, data: dict) -> bool:
        if self.db.get(EmailWebhookEvent, event_id):
            return False
        body = data.get("data") or {}
        if not isinstance(body, dict):
            raise ValueError("Invalid email event data")
        provider_id, event_type = body.get("email_id"), data.get("type")
        if not isinstance(provider_id, str) or not 0 < len(provider_id) <= 255 or event_type not in EVENT_STATES:
            raise ValueError("Unsupported email event")
        tags = body.get("tags") or {}
        if isinstance(tags, list):
            tags = {t.get("name"): t.get("value") for t in tags if isinstance(t, dict)}
        tagged_id = tags.get("delivery_id") if isinstance(tags, dict) else None
        try:
            delivery_id = UUID(tagged_id) if tagged_id else None
        except (ValueError, TypeError):
            delivery_id = None
        recipients = body.get("to") or []
        hashed = (
            address_hash(recipients[0])
            if isinstance(recipients, list) and recipients and isinstance(recipients[0], str)
            else None
        )
        try:
            source_at = datetime.fromisoformat(data.get("created_at", "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            source_at = None
        event = EmailWebhookEvent(
            event_id=event_id,
            provider_message_id=provider_id,
            delivery_id=delivery_id,
            event_type=event_type,
            recipient_hash=hashed,
            source_at=source_at,
            received_at=self.clock(),
        )
        try:
            with self.db.begin_nested():
                self.db.add(event)
                self.db.flush()
        except IntegrityError:
            self.db.rollback()
            return False
        outbox = self.db.exec(
            select(EmailOutbox).where(EmailOutbox.provider_message_id == provider_id).with_for_update()
        ).first()
        if not outbox and delivery_id:
            outbox = self.db.exec(
                select(EmailOutbox).where(EmailOutbox.delivery_id == delivery_id).with_for_update()
            ).first()
        if outbox:
            self._apply(outbox, event)
        elif EVENT_STATES[event_type] in BLOCKING_STATES and hashed:
            self._suppress(hashed, EVENT_STATES[event_type])
        self.db.commit()  # Receipt is durable before HTTP 200.
        return True

    def purge_payloads(self) -> int:
        from .personalization import purge_derived_data

        since = self.clock() - timedelta(days=self.cfg.email_payload_retention_days)
        result = self.db.execute(
            update(EmailOutbox).where(EmailOutbox.created_at < since).values(recipient=None, payload=None)
        )
        purge_derived_data(self.db, self.clock())
        self.db.commit()
        return result.rowcount


class _NoopScheduler:
    def schedule(self, *args, **kwargs):
        pass
