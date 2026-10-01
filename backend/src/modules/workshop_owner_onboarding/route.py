"""Workshop-owner onboarding — HTTP endpoints (API-201..API-204).

Routes only read request context and delegate to the service. Errors are
rendered by the app-level handler registered in ``main.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Response, status

from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.request_context import RequestContext
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.workshop_owner_auth.dependency import request_context

from . import openapi_examples, schemas
from .dependency import get_current_workshop_owner, get_workshop_onboarding_service
from .service import WorkshopOnboardingService

router = APIRouter(prefix="/workshop-owner", tags=["workshop-owner-onboarding"])


@router.post(
    "/oauth/sign-in",
    response_model=schemas.SignInEnvelope,
    summary="Workshop owner: sign in with Firebase (Google) and sync the account",
)
async def sign_in(
    response: Response,
    claims: Annotated[dict, Depends(verify_firebase_token)],
    context: Annotated[RequestContext, Depends(request_context)],
    service: Annotated[WorkshopOnboardingService, Depends(get_workshop_onboarding_service)],
) -> schemas.SignInEnvelope:
    data, is_new = service.sign_in(claims, context)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return schemas.SignInEnvelope(data=data)


@router.get(
    "/onboarding",
    response_model=schemas.OnboardingEnvelope,
    summary="Workshop owner: current onboarding state and saved data",
)
async def get_onboarding(
    owner: Annotated[WorkshopOwner, Depends(get_current_workshop_owner)],
    service: Annotated[WorkshopOnboardingService, Depends(get_workshop_onboarding_service)],
) -> schemas.OnboardingEnvelope:
    return schemas.OnboardingEnvelope(data=service.get_onboarding(owner))


@router.put(
    "/onboarding/profile",
    response_model=schemas.ProfileUpdateEnvelope,
    summary="Workshop owner: save full name, phone, national id (CCCD) and consent",
)
async def update_profile(
    body: Annotated[
        schemas.WorkshopProfileUpdateRequest,
        Body(openapi_examples=openapi_examples.PROFILE_UPDATE_EXAMPLES),
    ],
    owner: Annotated[WorkshopOwner, Depends(get_current_workshop_owner)],
    service: Annotated[WorkshopOnboardingService, Depends(get_workshop_onboarding_service)],
) -> schemas.ProfileUpdateEnvelope:
    return schemas.ProfileUpdateEnvelope(data=service.update_profile(owner, body))


@router.post(
    "/onboarding/workshop-verification",
    response_model=schemas.VerificationEnvelope,
    summary="Workshop owner: submit operating data and verify with the manufacturer",
)
async def submit_workshop_verification(
    body: Annotated[
        schemas.WorkshopVerificationRequest,
        Body(openapi_examples=openapi_examples.WORKSHOP_VERIFICATION_EXAMPLES),
    ],
    response: Response,
    owner: Annotated[WorkshopOwner, Depends(get_current_workshop_owner)],
    service: Annotated[WorkshopOnboardingService, Depends(get_workshop_onboarding_service)],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            openapi_examples=openapi_examples.IDEMPOTENCY_KEY_EXAMPLES,
        ),
    ],
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> schemas.VerificationEnvelope:
    data, http_status = await service.submit_verification(
        owner, body, idempotency_key=idempotency_key, trace_id=x_request_id
    )
    response.status_code = http_status
    return schemas.VerificationEnvelope(data=data)
