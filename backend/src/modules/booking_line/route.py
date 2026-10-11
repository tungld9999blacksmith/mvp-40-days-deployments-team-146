"""Two-tier booking pricing — HTTP endpoints (docs/designs/bao-gia-hai-tang.md).

Vehicle owner: read the lines of a booking, decide on PROPOSED lines, dispute a
decision the workshop recorded by phone. Workshop owner: confirm reference prices
after check-in, propose / edit / withdraw extras, record the owner's answer given
by phone, sign photo uploads.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from src.common.core.identity.vehicle_user import VehicleUser
from src.config import get_settings
from src.modules.booking.dependency import require_active_vehicle_owner
from src.modules.workshop_board.dependency import OwnerWorkshop, get_owner_workshop

from . import schemas
from .dependency import get_booking_line_service
from .service import BookingLineService

router = APIRouter(tags=["booking-lines"])
workshop_router = APIRouter(prefix="/workshop-owner", tags=["booking-lines"])

Owner = Annotated[VehicleUser, Depends(require_active_vehicle_owner)]
Scope = Annotated[OwnerWorkshop, Depends(get_owner_workshop)]
Lines = Annotated[BookingLineService, Depends(get_booking_line_service)]
BookingIdPath = Annotated[UUID, Path(alias="bookingId")]
LineIdPath = Annotated[UUID, Path(alias="lineId")]


@router.get(
    "/pricing-flow",
    response_model=schemas.PricingFlowEnvelope,
    summary="Pricing flow of new bookings, so the apps hide the legacy quote actions under two_tier",
)
def get_pricing_flow() -> schemas.PricingFlowEnvelope:
    return schemas.PricingFlowEnvelope(data=schemas.PricingFlowOut(quote_flow=get_settings().quote_flow))


# ── vehicle owner ───────────────────────────────────────────────────────────
@router.get(
    "/bookings/{bookingId}/lines",
    response_model=schemas.LinesEnvelope,
    summary="Price lines of my booking: package, extras, totals",
)
def get_my_booking_lines(user: Owner, lines: Lines, booking_id: BookingIdPath) -> schemas.LinesEnvelope:
    return schemas.LinesEnvelope(data=lines.view(lines.owned_booking(user, booking_id)))


@router.post(
    "/bookings/{bookingId}/lines/{lineId}/decision",
    response_model=schemas.LinesEnvelope,
    summary="Approve or decline a line the workshop proposed (version must match what I saw)",
)
def decide_booking_line(
    payload: schemas.DecideRequest, user: Owner, lines: Lines, booking_id: BookingIdPath, line_id: LineIdPath
) -> schemas.LinesEnvelope:
    return schemas.LinesEnvelope(data=lines.decide(user, booking_id, line_id, payload))


@router.post(
    "/bookings/{bookingId}/lines/{lineId}/dispute",
    response_model=schemas.LinesEnvelope,
    summary='"Tôi không đồng ý": undo a decision the workshop recorded by phone (before COMPLETE)',
)
def dispute_booking_line(
    payload: schemas.DisputeRequest, user: Owner, lines: Lines, booking_id: BookingIdPath, line_id: LineIdPath
) -> schemas.LinesEnvelope:
    return schemas.LinesEnvelope(data=lines.dispute(user, booking_id, line_id, payload))


# ── workshop owner ──────────────────────────────────────────────────────────
@workshop_router.get(
    "/bookings/{bookingId}/lines",
    response_model=schemas.LinesEnvelope,
    summary="Price lines of a booking of my workshop",
)
def get_workshop_booking_lines(scope: Scope, lines: Lines, booking_id: BookingIdPath) -> schemas.LinesEnvelope:
    return schemas.LinesEnvelope(data=lines.view(lines.workshop_booking(scope.workshop, booking_id)))


@workshop_router.post(
    "/bookings/{bookingId}/lines/{lineId}/confirm",
    response_model=schemas.LinesEnvelope,
    summary="Confirm a reference price after check-in (above the reference → owner decides)",
)
async def confirm_package_line(
    payload: schemas.ConfirmPackageRequest, scope: Scope, lines: Lines, booking_id: BookingIdPath, line_id: LineIdPath
) -> schemas.LinesEnvelope:
    scope.require_active()
    return schemas.LinesEnvelope(
        data=await lines.confirm_package(scope.owner, scope.workshop, booking_id, line_id, payload)
    )


@workshop_router.post(
    "/bookings/{bookingId}/lines",
    response_model=schemas.LinesEnvelope,
    status_code=201,
    summary="Propose an extra item found at the workshop",
)
async def propose_extra_line(
    payload: schemas.ProposeExtraRequest, scope: Scope, lines: Lines, booking_id: BookingIdPath
) -> schemas.LinesEnvelope:
    scope.require_active()
    return schemas.LinesEnvelope(data=await lines.propose_extra(scope.owner, scope.workshop, booking_id, payload))


@workshop_router.patch(
    "/bookings/{bookingId}/lines/{lineId}",
    response_model=schemas.LinesEnvelope,
    summary="Edit a line still waiting for the owner (sent again as a new version)",
)
async def edit_booking_line(
    payload: schemas.EditLineRequest, scope: Scope, lines: Lines, booking_id: BookingIdPath, line_id: LineIdPath
) -> schemas.LinesEnvelope:
    scope.require_active()
    return schemas.LinesEnvelope(data=await lines.edit_line(scope.owner, scope.workshop, booking_id, line_id, payload))


@workshop_router.post(
    "/bookings/{bookingId}/lines/{lineId}/phone-decision",
    response_model=schemas.LinesEnvelope,
    summary="Record the owner's answer given by phone (the owner is told and can dispute it)",
)
async def record_phone_decision(
    payload: schemas.PhoneDecisionRequest, scope: Scope, lines: Lines, booking_id: BookingIdPath, line_id: LineIdPath
) -> schemas.LinesEnvelope:
    scope.require_active()
    return schemas.LinesEnvelope(
        data=await lines.record_phone_decision(scope.owner, scope.workshop, booking_id, line_id, payload)
    )


@workshop_router.post(
    "/bookings/{bookingId}/lines/{lineId}/withdraw",
    response_model=schemas.LinesEnvelope,
    summary="Withdraw an extra item still waiting for the owner",
)
def withdraw_booking_line(
    payload: schemas.WithdrawRequest, scope: Scope, lines: Lines, booking_id: BookingIdPath, line_id: LineIdPath
) -> schemas.LinesEnvelope:
    scope.require_active()
    return schemas.LinesEnvelope(data=lines.withdraw(scope.workshop, booking_id, line_id, payload))


@workshop_router.post(
    "/bookings/{bookingId}/line-photos",
    response_model=schemas.PhotoUploadEnvelope,
    summary="Signed upload for one photo of an extra item (attach its key when proposing)",
)
def sign_line_photo_upload(
    payload: schemas.PhotoUploadRequest, scope: Scope, lines: Lines, booking_id: BookingIdPath
) -> schemas.PhotoUploadEnvelope:
    scope.require_active()
    upload = lines.sign_photo_upload(scope.workshop, booking_id, payload.content_type)
    return schemas.PhotoUploadEnvelope(
        data=schemas.PhotoUploadOut(key=upload.key, upload_url=upload.url, token=upload.token)
    )
