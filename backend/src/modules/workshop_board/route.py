"""Workshop Board — HTTP endpoints for the workshop owner (us-037 API-WB-01..08, us-057 API-PG-01/02)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from src.common.core.maintenance.service_progress import ServiceStage
from src.modules.service_progress.dependency import get_service_progress_service
from src.modules.service_progress.schemas import AppendProgressRequest, ProgressEnvelope
from src.modules.service_progress.service import ServiceProgressService

from . import schemas
from .dependency import OwnerWorkshop, get_board_service, get_owner_workshop
from .service import WorkshopBoardService

router = APIRouter(prefix="/workshop-owner", tags=["workshop-board"])

Scope = Annotated[OwnerWorkshop, Depends(get_owner_workshop)]
Board = Annotated[WorkshopBoardService, Depends(get_board_service)]
Progress = Annotated[ServiceProgressService, Depends(get_service_progress_service)]
BookingIdPath = Annotated[UUID, Path(alias="bookingId")]


@router.get(
    "/bookings",
    response_model=schemas.BoardListEnvelope,
    summary="Bookings of my workshop by date range, with summary (UC-801)",
)
async def list_board_bookings(
    scope: Scope,
    board: Board,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
    status: Annotated[list[schemas.BookingStatusIn] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=20)] = None,
) -> schemas.BoardListEnvelope:
    data = board.list_bookings(
        scope.workshop,
        from_=from_,
        to=to,
        statuses=[s.value for s in status] if status else None,
        q=q,
    )
    return schemas.BoardListEnvelope(data=data)


# Declared before ``/bookings/{bookingId}`` so ``by-code`` is not parsed as a UUID.
@router.get(
    "/bookings/by-code/{bookingCode}",
    response_model=schemas.ByCodeEnvelope,
    summary="Find a booking of my workshop by code / QR for check-in (UC-803)",
)
async def find_board_booking_by_code(
    scope: Scope,
    board: Board,
    booking_code: Annotated[str, Path(alias="bookingCode", max_length=40)],
) -> schemas.ByCodeEnvelope:
    return schemas.ByCodeEnvelope(data=board.by_code(scope.workshop, booking_code))


@router.get(
    "/bookings/{bookingId}",
    response_model=schemas.BoardDetailEnvelope,
    summary="Booking detail with status history and allowed actions",
)
async def get_board_booking(scope: Scope, board: Board, booking_id: BookingIdPath) -> schemas.BoardDetailEnvelope:
    return schemas.BoardDetailEnvelope(data=board.detail(scope.workshop, booking_id))


@router.post(
    "/bookings/{bookingId}/transitions",
    response_model=schemas.TransitionEnvelope,
    summary="ACCEPT / REJECT / CHECK_IN / START / COMPLETE / CANCEL (BR-802)",
)
async def transition_board_booking(
    payload: schemas.TransitionRequest,
    scope: Scope,
    board: Board,
    booking_id: BookingIdPath,
) -> schemas.TransitionEnvelope:
    data = await board.transition(scope.owner, scope.workshop, booking_id, payload)
    return schemas.TransitionEnvelope(data=data)


@router.get(
    "/capacity",
    response_model=schemas.CapacityEnvelope,
    summary="Capacity per day × slot: occupied, blocked, remaining (UC-806)",
)
async def get_capacity(
    scope: Scope,
    board: Board,
    from_: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=7)] = 7,
) -> schemas.CapacityEnvelope:
    return schemas.CapacityEnvelope(data=board.capacity(scope.workshop, from_=from_, days=days))


@router.put(
    "/slot-blocks",
    response_model=schemas.SlotBlockEnvelope,
    summary="Set the number of blocked slots for one time slot; 0 removes it (BR-809)",
)
async def put_slot_block(payload: schemas.SlotBlockRequest, scope: Scope, board: Board) -> schemas.SlotBlockEnvelope:
    data = await board.set_slot_block(scope.owner, scope.workshop, payload)
    return schemas.SlotBlockEnvelope(data=data)


@router.get(
    "/booking-settings",
    response_model=schemas.BookingSettingsEnvelope,
    summary="Booking confirmation mode of my workshop (UC-807)",
)
async def get_booking_settings(scope: Scope, board: Board) -> schemas.BookingSettingsEnvelope:
    return schemas.BookingSettingsEnvelope(data=board.settings(scope.workshop))


@router.put(
    "/booking-settings",
    response_model=schemas.BookingSettingsEnvelope,
    summary="Switch AUTO / MANUAL confirmation for new bookings (BR-811)",
)
async def put_booking_settings(
    payload: schemas.BookingSettingsRequest, scope: Scope, board: Board
) -> schemas.BookingSettingsEnvelope:
    data = board.update_settings(scope.workshop, payload.confirmation_mode.value)
    return schemas.BookingSettingsEnvelope(data=data)


# ── us-057 — service progress (API-PG-01/02) ────────────────────────────────
@router.get(
    "/bookings/{bookingId}/progress",
    response_model=ProgressEnvelope,
    summary="Progress timeline + next valid stages (SCR-1301)",
)
async def get_board_progress(
    scope: Scope, board: Board, progress: Progress, booking_id: BookingIdPath
) -> ProgressEnvelope:
    booking = board.booking_of(scope.workshop, booking_id)
    return ProgressEnvelope(data=progress.timeline(booking, for_workshop=True))


@router.post(
    "/bookings/{bookingId}/progress",
    response_model=ProgressEnvelope,
    status_code=201,
    summary="Append a progress stage (UC-1302, BR-1302, BR-1303)",
)
async def append_board_progress(
    payload: AppendProgressRequest,
    scope: Scope,
    board: Board,
    progress: Progress,
    booking_id: BookingIdPath,
) -> ProgressEnvelope:
    progress.ensure_enabled()
    booking = board.booking_of(scope.workshop, booking_id)
    board.require_active(scope.workshop)
    expected = payload.expected_current_stage
    data = await progress.append(
        booking,
        scope.owner.id,
        stage=ServiceStage(payload.stage.value.lower()),
        note=payload.note,
        expected_current=ServiceStage(expected.value.lower()) if expected else None,
    )
    return ProgressEnvelope(data=data)
