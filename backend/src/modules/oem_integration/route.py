"""OEM integration module — webhook endpoint (API-VEH-004).

Called by the manufacturer, not by the app: authenticated with an HMAC
signature instead of a Firebase token.
"""

from __future__ import annotations

from typing import Annotated

from ev_contracts import (
    WEBHOOK_EVENT_ID_HEADER,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
)
from fastapi import APIRouter, Depends, Request, status

from . import schemas
from .dependency import get_webhook_service
from .service import OemWebhookService

router = APIRouter(prefix="/integrations/oem", tags=["oem-integration"])


@router.post(
    "/webhooks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=schemas.WebhookAckEnvelope,
    summary="Receive a signed 'vehicle data changed' signal from the manufacturer",
)
async def receive_oem_webhook(
    request: Request,
    service: Annotated[OemWebhookService, Depends(get_webhook_service)],
) -> schemas.WebhookAckEnvelope:
    # The signature covers the raw bytes, so the body is read before any parsing.
    raw_body = await request.body()
    result = await service.handle(
        event_id=request.headers.get(WEBHOOK_EVENT_ID_HEADER),
        timestamp=request.headers.get(WEBHOOK_TIMESTAMP_HEADER),
        signature=request.headers.get(WEBHOOK_SIGNATURE_HEADER),
        raw_body=raw_body,
    )
    return schemas.WebhookAckEnvelope(
        data=schemas.WebhookAckOut(
            event_id=result.event_id,
            accepted=result.accepted,
            duplicate=result.duplicate,
            ignored=result.ignored,
        )
    )
