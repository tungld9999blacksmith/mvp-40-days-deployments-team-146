"""Follow-up & support tickets — HTTP endpoints (us-041 API-FU-01..07)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from src.common.core.crm.support_ticket import SupportTicketPriority, SupportTicketStatus
from src.common.core.identity.vehicle_user import VehicleUser
from src.modules.booking.dependency import require_active_vehicle_owner
from src.modules.workshop_board.dependency import OwnerWorkshop, get_owner_workshop

from . import schemas
from .dependency import get_follow_up_service, get_workshop_ticket_service
from .service import FollowUpService, WorkshopTicketService

router = APIRouter(tags=["follow-up"])
workshop_router = APIRouter(prefix="/workshop-owner", tags=["follow-up"])

Owner = Annotated[VehicleUser, Depends(require_active_vehicle_owner)]
FollowUps = Annotated[FollowUpService, Depends(get_follow_up_service)]
Scope = Annotated[OwnerWorkshop, Depends(get_owner_workshop)]
Tickets = Annotated[WorkshopTicketService, Depends(get_workshop_ticket_service)]
TicketIdPath = Annotated[UUID, Path(alias="ticketId")]


def _status(value: str | None) -> SupportTicketStatus | None:
    return SupportTicketStatus(value.lower()) if value else None


# ── vehicle owner ───────────────────────────────────────────────────────────
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
    summary="Answer the follow-up; an issue opens a support ticket (UC-902, UC-903)",
)
async def respond_follow_up(
    payload: schemas.RespondRequest,
    user: Owner,
    service: FollowUps,
    follow_up_id: Annotated[UUID, Path(alias="followUpId")],
) -> schemas.RespondEnvelope:
    data = await service.respond(user, follow_up_id, payload.rating, payload.comment)
    return schemas.RespondEnvelope(data=data)


@router.get(
    "/support-tickets",
    response_model=schemas.OwnerTicketListEnvelope,
    summary="My support tickets, newest first (BR-911)",
)
async def list_my_support_tickets(
    user: Owner,
    service: FollowUps,
    status: Annotated[schemas.TicketStatusIn | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
) -> schemas.OwnerTicketListEnvelope:
    data = service.list_tickets(
        user, status=_status(status.value if status else None), limit=limit, cursor=cursor
    )
    return schemas.OwnerTicketListEnvelope(data=data)


@router.get(
    "/support-tickets/{ticketId}",
    response_model=schemas.OwnerTicketEnvelope,
    summary="My support ticket detail (BR-911)",
)
async def get_my_support_ticket(
    user: Owner, service: FollowUps, ticket_id: TicketIdPath
) -> schemas.OwnerTicketEnvelope:
    return schemas.OwnerTicketEnvelope(data=service.get_ticket(user, ticket_id))


# ── workshop owner ──────────────────────────────────────────────────────────
@workshop_router.get(
    "/support-tickets",
    response_model=schemas.WorkshopTicketListEnvelope,
    summary="Support tickets of my workshop; high priority first (UC-904)",
)
async def list_workshop_support_tickets(
    scope: Scope,
    tickets: Tickets,
    status: Annotated[list[schemas.TicketStatusIn] | None, Query()] = None,
    priority: Annotated[schemas.TicketPriorityIn | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
) -> schemas.WorkshopTicketListEnvelope:
    data = tickets.list(
        scope.owner,
        scope.workshop.id,
        statuses=[SupportTicketStatus(s.value.lower()) for s in status] if status else None,
        priority=SupportTicketPriority(priority.value.lower()) if priority else None,
        limit=limit,
        cursor=cursor,
    )
    return schemas.WorkshopTicketListEnvelope(data=data)


@workshop_router.get(
    "/support-tickets/{ticketId}",
    response_model=schemas.WorkshopTicketEnvelope,
    summary="Support ticket detail with feedback and classification",
)
async def get_workshop_support_ticket(
    scope: Scope, tickets: Tickets, ticket_id: TicketIdPath
) -> schemas.WorkshopTicketEnvelope:
    return schemas.WorkshopTicketEnvelope(data=tickets.get(scope.owner, scope.workshop.id, ticket_id))


@workshop_router.post(
    "/support-tickets/{ticketId}/transitions",
    response_model=schemas.TicketTransitionEnvelope,
    summary="START / RESOLVE a support ticket (BR-910)",
)
async def transition_workshop_support_ticket(
    payload: schemas.TicketTransitionRequest,
    scope: Scope,
    tickets: Tickets,
    ticket_id: TicketIdPath,
) -> schemas.TicketTransitionEnvelope:
    data = await tickets.transition(
        scope.owner,
        scope.workshop.id,
        ticket_id,
        action=payload.action.value,
        expected_status=payload.expected_status.value,
        resolution_note=payload.resolution_note,
    )
    return schemas.TicketTransitionEnvelope(data=data)
