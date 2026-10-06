"""Quick booking — HTTP endpoints (us-061 API-QB-01..04).

``API-QB-02`` (confirm) is the only way a chat proposal becomes a booking (BR-1509).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from src.modules.conversation.dependency import get_current_user_id

from . import schemas
from .dependency import get_quick_booking_service
from .service import QuickBookingService

router = APIRouter(prefix="/conversations", tags=["quick-booking"])

ConversationId = Annotated[UUID, Path(alias="conversationId")]
ProposalId = Annotated[UUID, Path(alias="proposalId")]
Service = Annotated[QuickBookingService, Depends(get_quick_booking_service)]
UserId = Annotated[int, Depends(get_current_user_id)]


@router.post(
    "/{conversationId}/quick-booking",
    response_model=schemas.QuickBookingEnvelope,
    status_code=201,
    summary="Quick booking chip: build a proposal card from the vehicle's real data (UC-1501)",
)
async def quick_booking(
    payload: schemas.QuickBookingRequest,
    conversation_id: ConversationId,
    service: Service,
    user_id: UserId,
) -> schemas.QuickBookingEnvelope:
    return schemas.QuickBookingEnvelope(data=await service.propose_quick(user_id, conversation_id, payload))


@router.post(
    "/{conversationId}/booking-proposals/{proposalId}/confirm",
    response_model=schemas.ConfirmEnvelope,
    summary="Owner confirms a proposal: re-check the slot and create the booking (UC-1502)",
)
async def confirm_proposal(
    conversation_id: ConversationId,
    proposal_id: ProposalId,
    service: Service,
    user_id: UserId,
) -> schemas.ConfirmEnvelope:
    return schemas.ConfirmEnvelope(data=await service.confirm(user_id, conversation_id, proposal_id))


@router.post(
    "/{conversationId}/booking-proposals/{proposalId}/revise",
    response_model=schemas.ReviseEnvelope,
    status_code=201,
    summary="Change workshop / time: a new proposal replaces this one (UC-1503)",
)
async def revise_proposal(
    payload: schemas.ReviseRequest,
    conversation_id: ConversationId,
    proposal_id: ProposalId,
    service: Service,
    user_id: UserId,
) -> schemas.ReviseEnvelope:
    return schemas.ReviseEnvelope(data=await service.revise(user_id, conversation_id, proposal_id, payload))


@router.post(
    "/{conversationId}/booking-proposals/{proposalId}/cancel",
    response_model=schemas.CancelEnvelope,
    summary="Cancel a proposal; nothing is booked (UC-1504)",
)
async def cancel_proposal(
    conversation_id: ConversationId,
    proposal_id: ProposalId,
    service: Service,
    user_id: UserId,
) -> schemas.CancelEnvelope:
    return schemas.CancelEnvelope(data=await service.cancel(user_id, conversation_id, proposal_id))
