"""Notification module - HTTP endpoints (API-NOTI-001..003).

Spec: ``docs/specs/sprint-2/api/us-021-sprint-2-spec.api.md``.
"""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.notification import ReminderDelivery
from src.common.core.notification.email import EmailOutbox
from src.config import get_settings
from src.infrastructure.supabase.db import get_session
from src.modules.user_vehicle.dependency import get_user_vehicle_service, require_active_vehicle_owner
from src.modules.user_vehicle.service import UserVehicleService

from . import schemas
from .context_service import ReminderContextService
from .dependency import get_notification_feed_service, get_notification_settings_service
from .email_service import MaintenanceEmailAdapter
from .email_transport import verify_webhook
from .feed_service import NotificationFeedService
from .settings_service import NotificationSettingsService

router = APIRouter(prefix="/notification-settings", tags=["notification-settings"])


@router.get(
    "",
    response_model=schemas.NotificationSettingsEnvelope,
    summary="Reminder switch, lead days and channels of the signed-in owner",
)
def get_notification_settings(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[NotificationSettingsService, Depends(get_notification_settings_service)],
) -> schemas.NotificationSettingsEnvelope:
    return schemas.NotificationSettingsEnvelope(data=service.get(user))


@router.put(
    "",
    response_model=schemas.NotificationSettingsEnvelope,
    summary="Save reminder switch, lead days and channels",
)
def update_notification_settings(
    payload: schemas.NotificationSettingsUpdateIn,
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[NotificationSettingsService, Depends(get_notification_settings_service)],
) -> schemas.NotificationSettingsEnvelope:
    return schemas.NotificationSettingsEnvelope(data=service.update(user, payload))


feed_router = APIRouter(prefix="/notifications", tags=["notifications"])


@feed_router.get(
    "",
    response_model=schemas.NotificationFeedEnvelope,
    summary="In-app feed: reminders, quote results, booking updates, appointment reminders and surveys (last 90 days)",
)
def list_notifications(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[NotificationFeedService, Depends(get_notification_feed_service)],
) -> schemas.NotificationFeedEnvelope:
    return schemas.NotificationFeedEnvelope(data=service.list_for_user(user))


@feed_router.get("/reminders/{reminder_id}")
def get_reminder_context(
    reminder_id: UUID,
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    db: Annotated[Session, Depends(get_session)],
    vehicles: Annotated[UserVehicleService, Depends(get_user_vehicle_service)],
):
    return {"data": ReminderContextService(db, vehicles).get(user, reminder_id)}


@feed_router.get("/email-outbox")
def get_mock_email_outbox(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    db: Annotated[Session, Depends(get_session)],
):
    cfg = get_settings()
    items = []
    if cfg.email_mode == "mock":
        rows = db.exec(
            select(EmailOutbox, ReminderDelivery)
            .join(ReminderDelivery, ReminderDelivery.id == EmailOutbox.delivery_id)
            .where(EmailOutbox.user_id == user.user_id, EmailOutbox.mode == "mock")
            .order_by(EmailOutbox.created_at.desc())
            .limit(50)
        ).all()
        for outbox, delivery in rows:
            if not outbox.payload:
                continue
            items.append(
                {
                    "id": str(delivery.id),
                    "reminderId": str(delivery.reminder_id),
                    "status": delivery.status.name,
                    "deliveryState": outbox.delivery_state,
                    "attempts": delivery.attempts,
                    "errorCode": delivery.error_code,
                    "sentAt": delivery.sent_at.isoformat() if delivery.sent_at else None,
                    "payload": {k: outbox.payload.get(k) for k in ("subject", "body", "html", "link")},
                }
            )
    return {"data": {"items": items, "mode": cfg.email_mode, "canRunReminders": False}}


@feed_router.post("/email/webhook")
async def email_webhook(request: Request, db: Annotated[Session, Depends(get_session)]):
    cfg = get_settings()
    if not cfg.resend_webhook_secret:
        raise HTTPException(503, "Email webhook is not configured.")
    raw = await request.body()
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, "Webhook payload too large.")
    try:
        event_id = verify_webhook(raw, request.headers, cfg.resend_webhook_secret)
    except ValueError:
        raise HTTPException(401, "Invalid webhook signature.") from None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid event")
        handled = await run_in_threadpool(MaintenanceEmailAdapter(db, cfg).record_webhook, event_id, data)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, "Invalid email event.") from None
    return {"data": {"received": True, "duplicate": not handled}}
