"""API endpoints: webhook configuration and manual test events (demo tooling)."""

from ev_contracts import WebhookEventType
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..service import VehicleService
from ..webhooks import load_settings, send_event

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class TestEventRequest(BaseModel):
    event_type: WebhookEventType
    vehicle_id: str


@router.get("/config", summary="Current outgoing webhook configuration (secret hidden)")
def get_config():
    settings = load_settings()
    return {
        "enabled": settings.enabled,
        "url": settings.url,
        "secret_configured": bool(settings.secret),
        "usage_min_interval_seconds": settings.usage_min_interval_seconds,
    }


@router.post(
    "/test-events",
    summary="Send one signed webhook to EV Care now and return the delivery result",
)
async def send_test_event(
    body: TestEventRequest,
    session: Session = Depends(get_session),
):
    if not VehicleService(session).get_vehicle(body.vehicle_id):
        raise HTTPException(404, f"Vehicle {body.vehicle_id} not found")

    result = await send_event(body.event_type, body.vehicle_id)
    if result is None:
        raise HTTPException(409, "Webhooks are disabled: set MOCK_WEBHOOK_URL")
    return {
        "event_id": result.event_id,
        "delivered": result.delivered,
        "status_code": result.status_code,
        "attempts": result.attempts,
        "error": result.error,
    }
