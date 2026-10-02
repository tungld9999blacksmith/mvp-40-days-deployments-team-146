"""Booking module — HTTP endpoints for the vehicle owner.

API-BK-01..04 (F6, us-029), the booking ticket / reminder actions (us-033
API-BR-01..03), my bookings + reschedule (us-053 API-BT-01..04) and the progress
timeline (us-057 API-PG-03). One capacity service backs both these endpoints and
the AI-004 booking tools (BR-011). Workshop-side actions live in ``workshop_board``.
"""

from __future__ import annotations

from datetime import date, time
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response

from src.common.core.identity.vehicle_user import VehicleUser
from src.modules.service_progress.dependency import get_service_progress_service
from src.modules.service_progress.schemas import ProgressEnvelope
from src.modules.service_progress.service import ServiceProgressService

from . import schemas
from .dependency import get_booking_service, get_ticket_service, require_active_vehicle_owner
from .service import BookingService
from .ticket import BookingTicketService

router = APIRouter(tags=["booking"])


@router.get(
    "/workshops/nearby",
    response_model=schemas.NearbyEnvelope,
    summary="Suggest active workshops near a location, with slot availability (UC-401)",
)
async def get_nearby_workshops(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[BookingService, Depends(get_booking_service)],
    anchor: Annotated[str | None, Query()] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
    query: Annotated[str | None, Query(max_length=200)] = None,
    province: Annotated[str | None, Query(max_length=100)] = None,
    user_vehicle_id: Annotated[UUID | None, Query(alias="userVehicleId")] = None,
    d: Annotated[date | None, Query(alias="date")] = None,
    time_slot: Annotated[time | None, Query(alias="timeSlot")] = None,
    limit: Annotated[int | None, Query(ge=1, le=10)] = None,
) -> schemas.NearbyEnvelope:
    data = await service.find_nearby(
        user,
        anchor_source=anchor,
        lat=lat,
        lng=lng,
        query=query,
        province=province,
        user_vehicle_id=user_vehicle_id,
        d=d,
        time_slot=time_slot,
        limit=limit,
    )
    return schemas.NearbyEnvelope(data=data)


@router.get(
    "/workshops/{workshopId}/availability",
    response_model=schemas.AvailabilityEnvelope,
    summary="Check slot availability (+ alternatives); issue a confirmation token (UC-402)",
)
async def get_availability(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[BookingService, Depends(get_booking_service)],
    workshop_id: Annotated[UUID, Path(alias="workshopId")],
    d: Annotated[date, Query(alias="date")],
    time_slot: Annotated[time | None, Query(alias="timeSlot")] = None,
    with_alternatives: Annotated[bool, Query(alias="withAlternatives")] = True,
    reschedule_booking_id: Annotated[UUID | None, Query(alias="rescheduleBookingId")] = None,
) -> schemas.AvailabilityEnvelope:
    data = await service.check_availability(
        user,
        workshop_id,
        d,
        time_slot,
        with_alternatives=with_alternatives,
        reschedule_booking_id=reschedule_booking_id,
    )
    return schemas.AvailabilityEnvelope(data=data)


@router.post(
    "/bookings",
    response_model=schemas.BookingEnvelope,
    status_code=201,
    summary="Owner confirms → hold the slot; auto-confirm when the workshop allows (BK-03)",
)
async def create_booking(
    payload: schemas.HoldRequest,
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> schemas.BookingEnvelope:
    data = await service.create_hold(user, payload)
    return schemas.BookingEnvelope(data=data)


@router.delete(
    "/bookings/{bookingId}/hold",
    response_model=schemas.CancelEnvelope,
    summary="Cancel a held slot within the owner's 10-minute window (BK-04, BR-010)",
)
async def cancel_hold(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[BookingService, Depends(get_booking_service)],
    booking_id: Annotated[UUID, Path(alias="bookingId")],
) -> schemas.CancelEnvelope:
    data = service.cancel_hold(user, booking_id)
    return schemas.CancelEnvelope(data=data)


# ── us-053 / us-033 — the owner's bookings (API-BT-01..04, API-BR-01..03) ─────
# ``/bookings/by-code/...`` is declared before ``/bookings/{bookingId}`` so the
# literal segment is not parsed as a UUID.
@router.get(
    "/bookings",
    response_model=schemas.MyBookingsEnvelope,
    summary="My bookings — upcoming or past (UC-1202, BR-1213)",
)
async def list_my_bookings(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    tickets: Annotated[BookingTicketService, Depends(get_ticket_service)],
    scope: Annotated[Literal["UPCOMING", "PAST"], Query()] = "UPCOMING",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> schemas.MyBookingsEnvelope:
    data = tickets.list_for_user(user, scope=scope, limit=limit, cursor=cursor)
    return schemas.MyBookingsEnvelope(data=data)


@router.get(
    "/bookings/by-code/{bookingCode}",
    response_model=schemas.BookingByCodeEnvelope,
    summary="Open my ticket from the QR URL /c/{code} (BR-1203)",
)
async def find_my_booking_by_code(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    tickets: Annotated[BookingTicketService, Depends(get_ticket_service)],
    booking_code: Annotated[str, Path(alias="bookingCode", max_length=20)],
) -> schemas.BookingByCodeEnvelope:
    booking_id = tickets.find_by_code(user, booking_code)
    return schemas.BookingByCodeEnvelope(data=schemas.BookingByCodeData(booking_id=booking_id))


@router.get(
    "/bookings/{bookingId}",
    response_model=schemas.TicketEnvelope,
    summary="Booking ticket with the actions allowed now (UC-702, UC-1201)",
)
async def get_booking_ticket(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    tickets: Annotated[BookingTicketService, Depends(get_ticket_service)],
    booking_id: Annotated[UUID, Path(alias="bookingId")],
    src: Annotated[Literal["REMINDER_24H", "APP"] | None, Query()] = None,
) -> schemas.TicketEnvelope:
    return schemas.TicketEnvelope(data=tickets.get_ticket(user, booking_id, src=src))


@router.post(
    "/bookings/{bookingId}/attendance-confirmation",
    response_model=schemas.AttendanceEnvelope,
    summary="Owner confirms they will come (BR-708) — status unchanged",
)
async def confirm_attendance(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    tickets: Annotated[BookingTicketService, Depends(get_ticket_service)],
    booking_id: Annotated[UUID, Path(alias="bookingId")],
) -> schemas.AttendanceEnvelope:
    return schemas.AttendanceEnvelope(data=tickets.confirm_attendance(user, booking_id))


@router.post(
    "/bookings/{bookingId}/cancel",
    response_model=schemas.OwnerCancelEnvelope,
    summary="Owner cancels a confirmed booking; the slot is freed at once (BR-709)",
)
async def cancel_confirmed_booking(
    payload: schemas.OwnerCancelRequest,
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    tickets: Annotated[BookingTicketService, Depends(get_ticket_service)],
    booking_id: Annotated[UUID, Path(alias="bookingId")],
) -> schemas.OwnerCancelEnvelope:
    data = tickets.cancel_by_owner(user, booking_id, source=payload.source.value, reason=payload.reason)
    return schemas.OwnerCancelEnvelope(data=data)


@router.get(
    "/bookings/{bookingId}/qr",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
    summary="QR image of a confirmed booking (BR-1203)",
)
async def get_booking_qr(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    tickets: Annotated[BookingTicketService, Depends(get_ticket_service)],
    booking_id: Annotated[UUID, Path(alias="bookingId")],
) -> Response:
    return Response(
        content=tickets.qr_png(user, booking_id),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post(
    "/bookings/{bookingId}/reschedule",
    response_model=schemas.TicketEnvelope,
    summary="Move a confirmed booking to a new slot atomically (UC-1203, BR-1204..1211)",
)
async def reschedule_booking(
    payload: schemas.RescheduleRequest,
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[BookingService, Depends(get_booking_service)],
    tickets: Annotated[BookingTicketService, Depends(get_ticket_service)],
    booking_id: Annotated[UUID, Path(alias="bookingId")],
) -> schemas.TicketEnvelope:
    booking = await service.reschedule(user, booking_id, payload.confirmation_token, source=payload.source.value)
    return schemas.TicketEnvelope(data=tickets.ticket(booking))


@router.get(
    "/bookings/{bookingId}/progress",
    response_model=ProgressEnvelope,
    summary="Service progress timeline of my booking (us-057 API-PG-03)",
)
async def get_my_booking_progress(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    tickets: Annotated[BookingTicketService, Depends(get_ticket_service)],
    progress: Annotated[ServiceProgressService, Depends(get_service_progress_service)],
    booking_id: Annotated[UUID, Path(alias="bookingId")],
) -> ProgressEnvelope:
    booking = tickets.owned_booking(user, booking_id)
    return ProgressEnvelope(data=progress.timeline(booking, for_workshop=False))
