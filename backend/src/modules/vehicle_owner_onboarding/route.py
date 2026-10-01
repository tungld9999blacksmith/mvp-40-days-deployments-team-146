"""Onboarding module — HTTP endpoints (API-001..API-005).

The route layer only reads request context and delegates to the service.
Business rules and DB access live in the service. Responses use the
``{"data": ...}`` envelope; errors are translated by the app-level handler
registered in ``main.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Response, status

from src.common.core.identity.vehicle_user import VehicleUser
from src.modules.oauth.dependency import verify_firebase_token

from . import openapi_examples, schemas
from .dependency import get_current_user, get_onboarding_service
from .service import OnboardingService

# Sign-in lives under /oauth (it is the entry point right after Google login);
# the rest of onboarding lives under /onboarding.
oauth_router = APIRouter(prefix="/oauth", tags=["onboarding"])
onboarding_router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@oauth_router.post(
    "/sign-in",
    response_model=schemas.SignInEnvelope,
    summary="Sign in with Firebase (Google) and sync the account",
)
async def sign_in(
    response: Response,
    claims: Annotated[dict, Depends(verify_firebase_token)],
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
) -> schemas.SignInEnvelope:
    data, is_new_user = await service.sign_in(claims)
    response.status_code = status.HTTP_201_CREATED if is_new_user else status.HTTP_200_OK
    return schemas.SignInEnvelope(data=data)


@onboarding_router.get(
    "",
    response_model=schemas.OnboardingEnvelope,
    summary="Get the current onboarding state and saved data",
)
async def get_onboarding(
    user: Annotated[VehicleUser, Depends(get_current_user)],
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
) -> schemas.OnboardingEnvelope:
    return schemas.OnboardingEnvelope(data=service.get_onboarding(user))


@onboarding_router.put(
    "/profile",
    response_model=schemas.ProfileUpdateEnvelope,
    summary="Save personal info, nearby location and data-processing consent",
)
async def update_profile(
    body: Annotated[
        schemas.ProfileUpdateRequest,
        Body(openapi_examples=openapi_examples.PROFILE_UPDATE_EXAMPLES),
    ],
    user: Annotated[VehicleUser, Depends(get_current_user)],
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
) -> schemas.ProfileUpdateEnvelope:
    return schemas.ProfileUpdateEnvelope(data=service.update_profile(user, body))


@onboarding_router.get(
    "/vehicle-models",
    response_model=schemas.VehicleModelsEnvelope,
    summary="List manufacturer vehicle models for the onboarding dropdown",
)
async def list_vehicle_models(
    _user: Annotated[VehicleUser, Depends(get_current_user)],
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
) -> schemas.VehicleModelsEnvelope:
    return schemas.VehicleModelsEnvelope(data=await service.list_vehicle_models())


@onboarding_router.post(
    "/vehicle-verification",
    response_model=schemas.VerificationEnvelope,
    summary="Submit vehicle info to the manufacturer for ownership verification",
)
async def submit_vehicle_verification(
    body: Annotated[
        schemas.VehicleVerificationRequest,
        Body(openapi_examples=openapi_examples.VEHICLE_VERIFICATION_EXAMPLES),
    ],
    response: Response,
    user: Annotated[VehicleUser, Depends(get_current_user)],
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            openapi_examples=openapi_examples.IDEMPOTENCY_KEY_EXAMPLES,
        ),
    ],
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> schemas.VerificationEnvelope:
    data, http_status = await service.submit_verification(
        user,
        body,
        idempotency_key=idempotency_key,
        trace_id=x_request_id,
    )
    response.status_code = http_status
    return schemas.VerificationEnvelope(data=data)
