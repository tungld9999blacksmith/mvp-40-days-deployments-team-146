"""Workshop price list — HTTP endpoints for the workshop owner (bao-gia-hai-tang D14)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session

from src.infrastructure.supabase.db import end_read_transaction, get_session
from src.modules.vehicle_owner_onboarding.dependency import get_oem_gateway
from src.modules.vehicle_owner_onboarding.ports import OemVehicleGateway
from src.modules.workshop_board.dependency import OwnerWorkshop, get_owner_workshop

from . import schemas
from .catalog import catalog_names
from .service import WorkshopPricingService

router = APIRouter(prefix="/workshop-owner/price-list", tags=["workshop-pricing"])


async def get_catalog_names(
    gateway: Annotated[OemVehicleGateway, Depends(get_oem_gateway)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    # The owner guard has already read the DB; do not wait on the manufacturer (up to
    # TIMEOUT_SECONDS) with that connection "idle in transaction" (see end_read_transaction).
    await run_in_threadpool(end_read_transaction, session)
    return await catalog_names(gateway)


def get_pricing_service(
    session: Annotated[Session, Depends(get_session)],
    names: Annotated[dict[str, str], Depends(get_catalog_names)],
) -> WorkshopPricingService:
    return WorkshopPricingService(session, catalog_names=names)


Scope = Annotated[OwnerWorkshop, Depends(get_owner_workshop)]
Pricing = Annotated[WorkshopPricingService, Depends(get_pricing_service)]


@router.get("", response_model=schemas.PriceListEnvelope, summary="My prices for one model, next to the reference")
def get_price_list(
    scope: Scope, pricing: Pricing, model_id: Annotated[str | None, Query(alias="modelId", max_length=64)] = None
) -> schemas.PriceListEnvelope:
    return schemas.PriceListEnvelope(data=pricing.price_list(scope.workshop, model_id))


@router.post(
    "/copy-reference",
    response_model=schemas.CopyReferenceEnvelope,
    summary="Quick start: copy the reference prices ± percent for items without a price",
)
def copy_reference_prices(
    payload: schemas.CopyReferenceRequest, scope: Scope, pricing: Pricing
) -> schemas.CopyReferenceEnvelope:
    scope.require_active()
    return schemas.CopyReferenceEnvelope(data=pricing.copy_reference(scope.workshop, payload))


@router.post(
    "/set",
    response_model=schemas.PriceListEnvelope,
    summary="Today's price of a service for all its codes (one per milestone)",
)
def set_service_price(payload: schemas.PriceSetRequest, scope: Scope, pricing: Pricing) -> schemas.PriceListEnvelope:
    scope.require_active()
    return schemas.PriceListEnvelope(data=pricing.set_prices(scope.workshop, payload))


@router.post("", response_model=schemas.PriceListEnvelope, status_code=201, summary="Add a price (no overlap)")
def create_price(payload: schemas.PriceCreateRequest, scope: Scope, pricing: Pricing) -> schemas.PriceListEnvelope:
    scope.require_active()
    return schemas.PriceListEnvelope(data=pricing.create(scope.workshop, payload))


@router.put("/{priceId}", response_model=schemas.PriceListEnvelope, summary="Change a price or its validity")
def update_price(
    payload: schemas.PriceUpdateRequest,
    scope: Scope,
    pricing: Pricing,
    price_id: Annotated[UUID, Path(alias="priceId")],
) -> schemas.PriceListEnvelope:
    scope.require_active()
    return schemas.PriceListEnvelope(data=pricing.update(scope.workshop, price_id, payload))
