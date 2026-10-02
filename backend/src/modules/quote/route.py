"""Quote module — HTTP endpoints (us-049 API-QT-01..05, API-QT-11..14)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.quote import QuoteStatus
from src.modules.user_vehicle.dependency import require_active_vehicle_owner
from src.modules.workshop_board.dependency import OwnerWorkshop, get_owner_workshop

from . import schemas
from .dependency import get_quote_service
from .service import QuoteService

router = APIRouter(prefix="/quotes", tags=["quotes"])
workshop_router = APIRouter(prefix="/workshop-owner/quotes", tags=["workshop-owner-quotes"])

Owner = Annotated[VehicleUser, Depends(require_active_vehicle_owner)]
Scope = Annotated[OwnerWorkshop, Depends(get_owner_workshop)]
Quotes = Annotated[QuoteService, Depends(get_quote_service)]
QuoteId = Annotated[UUID, Path(alias="quoteId")]


def _statuses(values: list[schemas.QuoteStatusIn] | None) -> list[QuoteStatus] | None:
    return [QuoteStatus(v.value.lower()) for v in values] if values else None


# ── vehicle owner ───────────────────────────────────────────────────────────
@router.post(
    "",
    response_model=schemas.QuoteEnvelope,
    status_code=201,
    summary="Draft a quote from (vehicle, workshop, milestone); prices come from F5 (BR-1101)",
)
async def create_quote(payload: schemas.CreateQuoteRequest, user: Owner, service: Quotes):
    return schemas.QuoteEnvelope(data=service.create(user, payload))


@router.get("", response_model=schemas.QuoteListEnvelope, summary="My quotes, newest first")
async def list_my_quotes(
    user: Owner,
    service: Quotes,
    user_vehicle_id: Annotated[UUID | None, Query(alias="userVehicleId")] = None,
    status: Annotated[list[schemas.QuoteStatusIn] | None, Query()] = None,
    unseen_result: Annotated[bool, Query(alias="unseenResult")] = False,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
):
    data = service.list_for_owner(
        user,
        user_vehicle_id=user_vehicle_id,
        statuses=_statuses(status),
        unseen_result=unseen_result,
        limit=limit,
        cursor=cursor,
    )
    return schemas.QuoteListEnvelope(data=data)


@router.get("/{quoteId}", response_model=schemas.QuoteEnvelope, summary="Quote detail + derived status")
async def get_my_quote(user: Owner, service: Quotes, quote_id: QuoteId):
    return schemas.QuoteEnvelope(data=service.get_for_owner(user, quote_id))


@router.post(
    "/{quoteId}/submit",
    response_model=schemas.QuoteEnvelope,
    summary="Send a draft to the workshop for approval (BR-1103, BR-1104)",
)
async def submit_quote(payload: schemas.SubmitQuoteRequest, user: Owner, service: Quotes, quote_id: QuoteId):
    return schemas.QuoteEnvelope(data=service.submit(user, quote_id))


@router.delete("/{quoteId}", status_code=204, response_class=Response, summary="Delete a draft (BR-1112)")
async def delete_quote(user: Owner, service: Quotes, quote_id: QuoteId) -> Response:
    service.delete_draft(user, quote_id)
    return Response(status_code=204)


# ── workshop owner ──────────────────────────────────────────────────────────
@workshop_router.get(
    "",
    response_model=schemas.WorkshopQuoteListEnvelope,
    summary="Quotes of my workshop — pending first by waiting time (BR-1110)",
)
async def list_workshop_quotes(
    scope: Scope,
    service: Quotes,
    status: Annotated[list[schemas.QuoteStatusIn] | None, Query()] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
):
    data = service.list_for_workshop(
        scope.workshop.id,
        statuses=_statuses(status),
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        cursor=cursor,
    )
    return schemas.WorkshopQuoteListEnvelope(data=data)


@workshop_router.get("/{quoteId}", response_model=schemas.WorkshopQuoteEnvelope, summary="Quote to review")
async def get_workshop_quote(scope: Scope, service: Quotes, quote_id: QuoteId):
    return schemas.WorkshopQuoteEnvelope(data=service.get_for_workshop(scope.workshop.id, quote_id))


@workshop_router.post(
    "/{quoteId}/approve",
    response_model=schemas.WorkshopQuoteEnvelope,
    summary="Approve, optionally adjusting line prices and validity (BR-1105, BR-1106)",
)
async def approve_quote(payload: schemas.ApproveQuoteRequest, scope: Scope, service: Quotes, quote_id: QuoteId):
    data = service.approve(scope.owner, scope.workshop.id, quote_id, payload)
    return schemas.WorkshopQuoteEnvelope(data=data)


@workshop_router.post(
    "/{quoteId}/reject",
    response_model=schemas.WorkshopQuoteEnvelope,
    summary="Reject with a reason (BR-1107)",
)
async def reject_quote(payload: schemas.RejectQuoteRequest, scope: Scope, service: Quotes, quote_id: QuoteId):
    data = service.reject(scope.owner, scope.workshop.id, quote_id, payload.reviewer_note)
    return schemas.WorkshopQuoteEnvelope(data=data)
