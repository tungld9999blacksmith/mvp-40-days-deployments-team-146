"""Post-service follow-up — HTTP endpoints (us-041 API-FU-01..02)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from src.common.core.identity.vehicle_user import VehicleUser
from src.modules.booking.dependency import require_active_vehicle_owner

from . import schemas
from .dependency import get_follow_up_service
from .service import FollowUpService

router = APIRouter(tags=["follow-up"])

Owner = Annotated[VehicleUser, Depends(require_active_vehicle_owner)]
FollowUps = Annotated[FollowUpService, Depends(get_follow_up_service)]


@router.get(
    "/follow-ups/{followUpId}",
    response_model=schemas.FollowUpEnvelope,
    summary="Post-service follow-up form and its state (UC-902)",
)
async def get_follow_up(
    user: Owner, service: FollowUps, follow_up_id: Annotated[UUID, Path(alias="followUpId")]
) -> schemas.FollowUpEnvelope:
    return schemas.FollowUpEnvelope(data=service.get(user, follow_up_id))


@router.post(
    "/follow-ups/{followUpId}/response",
    response_model=schemas.RespondEnvelope,
    summary="Answer the follow-up; a reported issue is recorded (UC-902, UC-903)",
)
async def respond_follow_up(
    payload: schemas.RespondRequest,
    user: Owner,
    service: FollowUps,
    follow_up_id: Annotated[UUID, Path(alias="followUpId")],
) -> schemas.RespondEnvelope:
    data = await service.respond(user, follow_up_id, payload.rating, payload.comment)
    return schemas.RespondEnvelope(data=data)
