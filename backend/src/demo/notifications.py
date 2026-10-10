"""Maintenance emails for the one-worker demo; no SQL, Redis or LLM dispatch."""

import asyncio
import logging
import os
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from src.common.core.maintenance.reminder import ReminderLevel
from src.modules.notification.channels import (
    RETRYABLE_ERRORS,
    DeliveryResult,
    NotificationMessage,
)
from src.modules.notification.email_templates import build_email_message
from src.modules.notification.email_transport import ResendEmailTransport, address_hash

from .notification_persistence import save_notifications
from .store import DemoError

logger = logging.getLogger(__name__)
TERMINAL_STATES = {"bounced", "complained", "suppressed", "failed"}
EVENT_STATES = {
    "email.sent": "accepted",
    "email.delivered": "delivered",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.suppressed": "suppressed",
    "email.failed": "failed",
    "email.delivery_delayed": "delayed",
}


class ChannelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: str
    enabled: StrictBool


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    reminders_enabled: StrictBool | None = Field(default=None, alias="remindersEnabled")
    reminder_lead_days: int | None = Field(default=None, alias="reminderLeadDays", ge=0, le=30, strict=True)
    channels: list[ChannelUpdate] | None = None


@dataclass(frozen=True)
class DemoEmailConfig:
    mode: str = "mock"
    app_url: str = "http://127.0.0.1:5173"
    sender: str = "EV Care <demo@example.com>"
    api_key: str = ""
    webhook_secret: str = ""
    poll_seconds: int = 60
    test_recipient: str = ""

    def __post_init__(self):
        if self.mode not in {"mock", "resend", "resend_test", "off"}:
            raise ValueError("DEMO_EMAIL_MODE must be mock, resend, resend_test or off")
        url = urlparse(self.app_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.query or url.fragment:
            raise ValueError("DEMO_EMAIL_APP_URL must be an absolute app URL")
        if self.poll_seconds < 30:
            raise ValueError("DEMO_REMINDER_INTERVAL_SECONDS must be at least 30")
        if self.mode == "resend" and not all((self.api_key, self.sender, self.webhook_secret)):
            raise ValueError("Resend mode requires RESEND_API_KEY, DEMO_EMAIL_FROM and RESEND_WEBHOOK_SECRET")
        if self.mode == "resend_test":
            if not all((self.api_key.strip(), self.sender.strip(), self.test_recipient.strip())):
                raise ValueError("Resend test requires RESEND_API_KEY, DEMO_EMAIL_FROM and DEMO_EMAIL_TEST_TO")
            if len(self.test_recipient) > 254 or not re.fullmatch(
                r"[^@\s,<>;]+@[^@\s,<>;]+\.[^@\s,<>;]+", self.test_recipient
            ):
                raise ValueError("DEMO_EMAIL_TEST_TO must contain exactly one email address")

    @classmethod
    def from_env(cls):
        mode = os.getenv("DEMO_EMAIL_MODE", "mock")
        if mode == "resend" and os.getenv("FIREBASE_AUTH_EMULATOR_HOST"):
            raise ValueError("Use mock email with Firebase Auth Emulator; Resend requires real Firebase identity")
        if mode == "resend" and os.getenv("DEMO_NOW"):
            raise ValueError("Resend requires the real clock; unset DEMO_NOW")
        if mode == "resend_test" and not os.getenv("FIREBASE_AUTH_EMULATOR_HOST"):
            raise ValueError("Resend test mode requires Firebase Auth Emulator")
        return cls(
            mode=mode,
            app_url=os.getenv("DEMO_EMAIL_APP_URL", "http://127.0.0.1:5173"),
            sender=os.getenv(
                "DEMO_EMAIL_FROM", "" if mode in {"resend", "resend_test"} else "EV Care <demo@example.com>"
            ),
            api_key=os.getenv("RESEND_API_KEY", ""),
            webhook_secret=os.getenv("RESEND_WEBHOOK_SECRET", ""),
            poll_seconds=int(os.getenv("DEMO_REMINDER_INTERVAL_SECONDS", "60")),
            test_recipient=os.getenv("DEMO_EMAIL_TEST_TO", "").strip(),
        )


class DemoNotificationService:
    def __init__(self, store, vehicles, maintenance, config=None, transport=None):
        self.store, self.vehicles, self.maintenance = store, vehicles, maintenance
        self.config = config or DemoEmailConfig()
        self.transport = transport or ResendEmailTransport(self.config.api_key)
        # A simulated date must never accelerate the real email cooldown/retry window.
        self.delivery_clock = lambda: datetime.now(UTC)

    def _recipient(self, user):
        email = user.get("email")
        if self.config.mode == "resend_test":
            if not email or address_hash(email) != address_hash(self.config.test_recipient):
                return None
            # Never dispatch to an address supplied by a token, API body or agent.
            return self.config.test_recipient
        return email

    def _cooldown_key(self, vehicle_id, recipient):
        if self.config.mode == "resend_test":
            # One configured mailbox shares a cooldown, even across emulator UIDs/vehicles.
            return f"resend_test:{address_hash(recipient)}"
        return vehicle_id

    def user(self, user_id):
        user = next((u for u in self.store.users.values() if u["userId"] == user_id), None)
        if not user:
            raise DemoError("UNAUTHORIZED", "Không tìm thấy tài khoản.", 401)
        return user

    def preferences(self, user):
        return self.store.notification_preferences.get(
            user["uid"], {"remindersEnabled": False, "reminderLeadDays": 2, "emailEnabled": False}
        )

    def settings(self, user_id):
        user = self.user(user_id)
        pref = self.preferences(user)
        email = self._recipient(user)
        verified = bool(email and user.get("emailVerified"))
        suppressed = bool(email and address_hash(email) in self.store.email_suppressions)
        available = self.config.mode != "off"
        return {
            "remindersEnabled": pref["remindersEnabled"],
            "reminderLeadDays": pref["reminderLeadDays"],
            "defaultReminderLeadDays": 2,
            "emailRecipient": email,
            "emailVerified": verified,
            "emailSuppressed": suppressed,
            "emailScope": "MAINTENANCE_REMINDER",
            "scope": "ALL_OWNED_VEHICLES",
            "emailTransport": self.config.mode,
            "emailTestRecipientMatched": bool(email) if self.config.mode == "resend_test" else None,
            "emailTestManualOnly": self.config.mode == "resend_test",
            "channels": [
                {
                    "channel": "EMAIL",
                    "enabled": pref["emailEnabled"],
                    "available": available,
                    "status": "COMING_SOON"
                    if not available
                    else "CONNECTED"
                    if verified and not suppressed
                    else "NOT_CONNECTED",
                }
            ],
        }

    def update(self, user_id, patch: SettingsUpdate):
        user = self.user(user_id)
        pref = dict(self.preferences(user))
        changes = patch.model_dump(exclude_unset=True)
        if any(v is None for v in changes.values()):
            raise DemoError("INVALID_REQUEST", "Cài đặt không được để null.", 422)
        if "reminders_enabled" in changes:
            pref["remindersEnabled"] = patch.reminders_enabled
        if "reminder_lead_days" in changes:
            pref["reminderLeadDays"] = patch.reminder_lead_days
        seen = set()
        for channel in patch.channels or []:
            if channel.channel != "EMAIL" or channel.channel in seen:
                raise DemoError("INVALID_CHANNEL", "Demo chỉ hỗ trợ kênh Email nhắc bảo dưỡng.", 422)
            seen.add(channel.channel)
            if channel.enabled:
                state = self.settings(user_id)
                if self.config.mode == "off":
                    raise DemoError("CHANNEL_NOT_AVAILABLE", "Kênh Email chưa được bật.", 422)
                if self.config.mode == "resend_test" and not state["emailTestRecipientMatched"]:
                    raise DemoError(
                        "EMAIL_TEST_RECIPIENT_MISMATCH",
                        "Tài khoản demo phải dùng email trùng địa chỉ gửi thử đã cấu hình.",
                        403,
                    )
                if not state["emailVerified"]:
                    raise DemoError("EMAIL_NOT_VERIFIED", "Cần email đăng nhập đã xác minh.", 422)
                if state["emailSuppressed"]:
                    raise DemoError("EMAIL_SUPPRESSED", "Email bị chặn do lỗi giao nhận trước đó.", 422)
            pref["emailEnabled"] = channel.enabled
        self.store.notification_preferences[user["uid"]] = pref
        save_notifications(self.store)
        return self.settings(user_id)

    def context(self, user_id, reminder_id):
        user = self.user(user_id)
        reminder = self.store.reminders.get(str(reminder_id))
        if not reminder or reminder["uid"] != user["uid"]:
            raise DemoError("REMINDER_NOT_FOUND", "Không tìm thấy lời nhắc.", 404)
        vehicle_id = reminder["userVehicleId"]
        self.vehicles.owned(user_id, vehicle_id)
        current_status = self.maintenance.calculate(user_id, vehicle_id)
        milestone = current_status.get("nextMilestone")
        deliveries = [
            {
                key: d.get(key)
                for key in (
                    "id",
                    "status",
                    "deliveryState",
                    "attempts",
                    "errorCode",
                    "providerMessageId",
                    "sentAt",
                    "mode",
                )
            }
            for d in self.store.email_deliveries.values()
            if d["reminderId"] == reminder_id
        ]
        return {
            "reminderId": reminder["id"],
            "userVehicleId": vehicle_id,
            "level": reminder["level"],
            "odoMilestoneKm": reminder["odoMilestoneKm"],
            "resolved": reminder["resolved"],
            "resolutionReason": reminder["resolutionReason"],
            "emailSkipReason": reminder.get("emailSkipReason"),
            "details": deepcopy(reminder["details"]),
            "currentStatus": current_status,
            "hasCurrentBooking": bool(
                milestone and self._has_booking(vehicle_id, milestone["odoMilestoneKm"], self.store.clock())
            ),
            "deliveries": deliveries,
        }

    def feed(self, user_id):
        uid = self.user(user_id)["uid"]
        return [
            {
                "id": f"reminder:{r['id']}",
                "kind": "MAINTENANCE_REMINDER",
                "occurredAt": r["createdAt"],
                "unread": False,
                "booking": None,
                "followUp": None,
                "reminder": {
                    k: deepcopy(r[k])
                    for k in ("userVehicleId", "level", "odoMilestoneKm", "resolved", "resolutionReason", "details")
                },
            }
            for r in self.store.reminders.values()
            if r["uid"] == uid
        ]

    def outbox(self, user_id):
        uid = self.user(user_id)["uid"]
        return sorted(
            [
                {
                    k: deepcopy(d.get(k))
                    for k in (
                        "id",
                        "reminderId",
                        "status",
                        "deliveryState",
                        "attempts",
                        "errorCode",
                        "sentAt",
                        "payload",
                    )
                }
                for d in self.store.email_deliveries.values()
                if d["uid"] == uid and d["mode"] == self.config.mode and d["mode"] in {"mock", "resend_test"}
            ],
            key=lambda d: d["sentAt"] or "",
            reverse=True,
        )

    def complete_maintenance(self, booking):
        vehicle = self.store.vehicles[booking["userVehicleId"]]
        for reminder in self.store.reminders.values():
            if reminder["userVehicleId"] == booking["userVehicleId"] and not reminder["resolved"]:
                self._resolve(reminder, "MAINTENANCE_COMPLETED")
            elif (
                reminder["userVehicleId"] == booking["userVehicleId"] and reminder["resolutionReason"] == "HAS_BOOKING"
            ):
                self._resolve(reminder, "MAINTENANCE_COMPLETED")
        vehicle.update(
            lastServiceOdo=max(vehicle["lastServiceOdo"] or 0, vehicle["odoKm"] or 0, booking["odoMilestone"]),
            lastServiceDate=self.store.clock().date().isoformat(),
            lastServiceSource="EV_CARE",
            lastServiceCenter=self.store.workshops[booking["workshopId"]]["name"],
        )
        from .persistence import save_registration

        save_registration(self.store)
        save_notifications(self.store)

    async def send_test_email(self, user_id):
        if self.config.mode != "resend_test":
            raise DemoError("EMAIL_TEST_DISABLED", "Chế độ gửi thử email thật chưa được bật.", 409)
        user = self.user(user_id)
        if not self._recipient(user):
            raise DemoError(
                "EMAIL_TEST_RECIPIENT_MISMATCH",
                "Tài khoản demo phải dùng email trùng địa chỉ gửi thử đã cấu hình.",
                403,
            )
        state = self.settings(user_id)
        if not state["remindersEnabled"] or not self.preferences(user)["emailEnabled"]:
            raise DemoError(
                "EMAIL_TEST_OPT_IN_REQUIRED", "Hãy bật nhắc bảo dưỡng và Email rồi lưu trước khi gửi thử.", 422
            )
        if not state["emailVerified"]:
            raise DemoError("EMAIL_NOT_VERIFIED", "Tài khoản demo chưa có email hợp lệ.", 422)
        if state["emailSuppressed"]:
            raise DemoError("EMAIL_SUPPRESSED", "Email bị chặn do lỗi giao nhận trước đó.", 422)
        return await self.run(user_id, send_test=True)

    async def run(self, user_id=None, *, send_test=False):
        if send_test and user_id is None:
            raise ValueError("Test email requires one authenticated owner")
        async with self.store.reminder_lock:
            now = self.store.clock()
            users = list(self.store.users.values())
            processed = 0
            for user in users:
                if user_id is not None and user["userId"] != user_id:
                    continue
                if user.get("accountStatus") != "active":
                    continue
                for vehicle in list(self.store.vehicles.values()):
                    if vehicle["userId"] != user["userId"] or not vehicle["active"] or not vehicle["verified"]:
                        continue
                    await self._vehicle(user, vehicle, now, send_test=send_test)
                    processed += 1
            save_notifications(self.store)
            return {"processedVehicles": processed, "checkedAt": now.isoformat(), "mode": self.config.mode}

    def _resolve(self, reminder, reason):
        reminder.update(resolved=True, resolutionReason=reason)

    def _has_booking(self, vehicle_id, milestone_km, now):
        return any(
            b["userVehicleId"] == vehicle_id
            and b.get("odoMilestone") == milestone_km
            and b["status"].upper() in {"PENDING", "CONFIRMED", "CHECKED_IN", "IN_PROGRESS"}
            and (b["bookingDate"] >= now.date().isoformat() or b["status"].upper() in {"CHECKED_IN", "IN_PROGRESS"})
            for b in self.store.bookings.values()
        )

    async def _vehicle(self, user, vehicle, now, *, send_test=False):
        vid = vehicle["userVehicleId"]
        result = self.maintenance.calculate(user["userId"], vid)
        milestone = result.get("nextMilestone")
        if not milestone:
            return
        km = milestone["odoMilestoneKm"]
        records = [r for r in self.store.reminders.values() if r["userVehicleId"] == vid and r["uid"] == user["uid"]]
        for record in records:
            if record["odoMilestoneKm"] != km and not record["resolved"]:
                self._resolve(record, "MILESTONE_CHANGED")
        current = [r for r in records if r["odoMilestoneKm"] == km]
        booked = self._has_booking(vid, km, now)
        if booked:
            for record in current:
                self._resolve(record, "HAS_BOOKING")
            return
        pref = self.preferences(user)
        if not pref["remindersEnabled"]:
            return
        remaining_km, days = result["remainingKm"], result["remainingDays"]
        # Demo's missing-ODO snapshot has a known service date and milestone.
        # Other UNKNOWN states are not suitable evidence for generating a reminder.
        if result["dueStatus"] == "UNKNOWN" and not (
            result.get("unknownReason") == "OEM_DATA_NOT_SYNCED"
            and remaining_km is None
            and days is not None
            and milestone.get("dueDate")
        ):
            return
        expired_km = remaining_km is not None and remaining_km <= 0
        expired_time = days is not None and days <= 0
        expired = expired_km or expired_time
        km_hit = (
            expired_km if expired else remaining_km is not None and remaining_km <= result["thresholds"]["dueSoonKm"]
        )
        time_hit = expired_time if expired else days is not None and days <= pref["reminderLeadDays"]
        if not km_hit and not time_hit:
            for record in current:
                self._resolve(record, "BEFORE_WINDOW")
            return
        level = "EXPIRED" if expired else "EARLY"
        if expired:
            for record in current:
                if record["level"] == "EARLY":
                    self._resolve(record, "SUPERSEDED")
        else:
            for record in current:
                if record["level"] == "EXPIRED":
                    self._resolve(record, "STATUS_CHANGED")
        odometer = result["odometer"] or {}
        details = {
            "templateVersion": "maintenance-v1",
            "capturedAt": now.isoformat(),
            "dueStatus": "OVERDUE" if expired else result["dueStatus"],
            "reason": "BOTH" if km_hit and time_hit else "KM" if km_hit else "TIME",
            "dueDate": milestone["dueDate"],
            "monthMilestone": milestone["monthMilestone"],
            "remainingKm": remaining_km,
            "remainingDays": days,
            "odometerKm": odometer.get("odoKm"),
            "odometerRecordedAt": odometer.get("recordedAt"),
            "odometerStale": odometer.get("isStale", False),
            "leadDays": pref["reminderLeadDays"],
            "dueSoonKm": result["thresholds"]["dueSoonKm"],
            "items": deepcopy(milestone["items"]),
        }
        reminder = next((r for r in current if r["level"] == level), None)
        if reminder is None:
            rid = str(uuid4())
            reminder = {
                "id": rid,
                "uid": user["uid"],
                "userVehicleId": vid,
                "odoMilestoneKm": km,
                "level": level,
                "createdAt": now.isoformat(),
                "resolved": False,
                "resolutionReason": None,
                "details": details,
            }
            self.store.reminders[rid] = reminder
        elif reminder["resolutionReason"] in {"HAS_BOOKING", "BEFORE_WINDOW", "SUPERSEDED", "STATUS_CHANGED"}:
            reminder.update(resolved=False, resolutionReason=None)
        if reminder["resolved"] or not pref["emailEnabled"] or self.config.mode == "off":
            return
        email = self._recipient(user)
        if not email or not user.get("emailVerified") or address_hash(email) in self.store.email_suppressions:
            reminder["emailSkipReason"] = (
                "NO_VERIFIED_RECIPIENT" if not email or not user.get("emailVerified") else "EMAIL_SUPPRESSED"
            )
            return
        if self.config.mode == "resend_test" and not send_test:
            return  # Background scans and agent settings never dispatch real test emails.
        delivery_now = self.delivery_clock() if self.config.mode == "resend_test" else now
        cooldown_key = self._cooldown_key(vid, email)
        delivery = next(
            (
                d
                for d in self.store.email_deliveries.values()
                if d["reminderId"] == reminder["id"] and d["mode"] == self.config.mode
            ),
            None,
        )
        if delivery is None:
            previous = self.store.email_cooldowns.get(cooldown_key)
            if previous and delivery_now - datetime.fromisoformat(previous) < timedelta(days=7):
                reminder["emailSkipReason"] = "COOLDOWN"
                return
            reminder["details"] = details
            did = str(uuid4())
            message = build_email_message(
                model_name=vehicle["modelName"],
                license_plate=vehicle["licensePlate"],
                milestone_km=km,
                level=ReminderLevel.EXPIRED if expired else ReminderLevel.EARLY,
                details=details,
                app_url=self.config.app_url,
                reminder_id=reminder["id"],
                delivery_id=did,
                recipient_hash=address_hash(email),
                sender=self.config.sender,
            )
            if self.config.mode == "resend_test":
                notice = "Đây là email thử của EV Care. Dữ liệu xe và mốc bảo dưỡng bên dưới là dữ liệu demo."
                message = replace(
                    message,
                    subject=f"[DEMO] {message.subject}",
                    body=f"{notice}\n\n{message.body}",
                    html=(message.html or "").replace("<h2>EV Care</h2>", f"<h2>EV Care — DEMO</h2><p>{notice}</p>", 1),
                )
            delivery = {
                "id": did,
                "uid": user["uid"],
                "reminderId": reminder["id"],
                "mode": self.config.mode,
                "recipientHash": address_hash(email),
                "payload": asdict(message),
                "attempts": 0,
                "status": "PENDING",
                "errorCode": None,
                "firstAttemptAt": None,
                "nextAttemptAt": None,
                "providerMessageId": None,
                "sentAt": None,
                "deliveryState": None,
            }
            self.store.email_deliveries[did] = delivery
        reminder.pop("emailSkipReason", None)
        await self._deliver(delivery, user, vid, delivery_now)

    async def _deliver(self, delivery, user, vid, now):
        if delivery["status"] == "SENT":
            return
        if delivery["attempts"] >= 3:
            if delivery["errorCode"] in RETRYABLE_ERRORS:
                delivery.update(errorCode="RECONCILIATION_REQUIRED", nextAttemptAt=None)
            return
        if delivery["status"] == "FAILED" and delivery["errorCode"] not in RETRYABLE_ERRORS:
            return
        if delivery["nextAttemptAt"] and datetime.fromisoformat(delivery["nextAttemptAt"]) > now:
            return
        if delivery["firstAttemptAt"] and now - datetime.fromisoformat(delivery["firstAttemptAt"]) >= timedelta(
            hours=23
        ):
            delivery.update(status="FAILED", errorCode="RECONCILIATION_REQUIRED", nextAttemptAt=None)
            return
        recipient = self._recipient(user)
        if (
            not recipient
            or delivery["mode"] != self.config.mode
            or delivery["recipientHash"] != address_hash(recipient)
        ):
            delivery.update(status="FAILED", errorCode="DELIVERY_CONTEXT_CHANGED", nextAttemptAt=None)
            return
        delivery["attempts"] += 1
        if delivery["firstAttemptAt"] is None:
            delivery["firstAttemptAt"] = now.isoformat()
            self.store.email_cooldowns[self._cooldown_key(vid, recipient)] = now.isoformat()
        delivery.update(
            status="FAILED",
            errorCode="UNAVAILABLE",
            nextAttemptAt=(now + timedelta(minutes=5 * delivery["attempts"])).isoformat(),
        )
        # Persist before network I/O: restart retries the same payload/key, within 23 hours.
        save_notifications(self.store)
        message = NotificationMessage(**delivery["payload"])
        if self.config.mode == "mock":
            response = DeliveryResult.sent(f"mock-{delivery['id']}")
        else:
            try:
                response = await self.transport.send(recipient, message)
            except Exception:  # noqa: BLE001 -- no provider exceptions or secrets in logs
                logger.warning("Demo email transport failed; delivery=%s", delivery["id"])
                response = DeliveryResult.failed("UNAVAILABLE")
        if response.provider_message_id and not delivery["providerMessageId"]:
            delivery["providerMessageId"] = response.provider_message_id
        if delivery["deliveryState"] is not None:
            # A signed webhook can already have established the provider outcome,
            # including while this request was awaiting a response or timed out.
            self._apply_events()
            save_notifications(self.store)
            return
        delivery.update(status=response.status.value.upper(), errorCode=response.error_code)
        if response.status.value.upper() == "SENT":
            delivery.update(
                sentAt=now.isoformat(),
                nextAttemptAt=None,
                deliveryState="mock" if self.config.mode == "mock" else "accepted",
            )
        elif not response.retryable or delivery["attempts"] >= 3:
            delivery["nextAttemptAt"] = None
            if response.retryable:
                delivery["errorCode"] = "RECONCILIATION_REQUIRED"
        self._apply_events()
        save_notifications(self.store)

    def webhook(self, event_id, payload):
        if event_id in self.store.email_events:
            return {"received": True, "duplicate": True}
        kind = payload.get("type")
        provider_id = (payload.get("data") or {}).get("email_id") if isinstance(payload.get("data"), dict) else None
        if kind not in EVENT_STATES:
            return {"received": True, "ignored": True}
        if not isinstance(provider_id, str) or not provider_id or len(provider_id) > 255:
            raise DemoError("INVALID_REQUEST", "Webhook thiếu mã email hợp lệ.", 422)
        tags = payload["data"].get("tags") or {}
        delivery_id = tags.get("delivery_id") if isinstance(tags, dict) else None
        try:
            occurred = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
            if occurred.utcoffset() is None:
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise DemoError("INVALID_REQUEST", "Webhook thiếu thời gian hợp lệ.", 422) from None
        self.store.email_events[event_id] = {
            "providerId": provider_id,
            "deliveryId": delivery_id if isinstance(delivery_id, str) else None,
            "state": EVENT_STATES[kind],
            "occurredAt": occurred.isoformat(),
            "applied": False,
        }
        self._apply_events()
        save_notifications(self.store)
        return {"received": True}

    def _apply_events(self):
        events = sorted(self.store.email_events.values(), key=lambda e: datetime.fromisoformat(e["occurredAt"]))
        for event in events:
            if event["applied"]:
                continue
            delivery = next(
                (d for d in self.store.email_deliveries.values() if d["providerMessageId"] == event["providerId"]), None
            )
            if delivery is None and event.get("deliveryId"):
                candidate = self.store.email_deliveries.get(event["deliveryId"])
                if (
                    candidate
                    and candidate["mode"] in {"resend", "resend_test"}
                    and candidate["providerMessageId"] is None
                ):
                    delivery = candidate
                    delivery["providerMessageId"] = event["providerId"]
            if delivery is None:
                continue  # Arrival before POST response: reconcile after the provider ID is stored.
            state = event["state"]
            if delivery["deliveryState"] not in TERMINAL_STATES and (
                state in TERMINAL_STATES or state == "delivered" or delivery["deliveryState"] != "delivered"
            ):
                delivery["deliveryState"] = state
                delivery.update(status="FAILED" if state in TERMINAL_STATES else "SENT", nextAttemptAt=None)
                delivery["errorCode"] = f"EMAIL_{state.upper()}" if state in TERMINAL_STATES else None
                if state not in TERMINAL_STATES and delivery["sentAt"] is None:
                    delivery["sentAt"] = event["occurredAt"]
            if state in {"bounced", "complained", "suppressed"}:
                self.store.email_suppressions[delivery["recipientHash"]] = state
            event["applied"] = True

    async def poll(self):
        while True:
            try:
                await self.run()
            except Exception:  # noqa: BLE001 -- keep the demo running, do not log recipient data
                logger.warning("Demo reminder scan failed")
            await asyncio.sleep(self.config.poll_seconds)
