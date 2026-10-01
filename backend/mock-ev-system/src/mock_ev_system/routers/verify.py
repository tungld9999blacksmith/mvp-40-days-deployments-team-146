"""API endpoint: Vehicle ownership verification.

This simulates the manufacturer's own ownership check. EV Care sends the
VIN, plate, model and the owner's identity (email + national id); the mock
matches them against its records and returns either the vehicle's technical
spec + warranties (verified) or a failure reason.

Keeping the matching here — instead of in the EV Care backend — mirrors the
real design where identity/ownership is authoritative on the manufacturer
side, and lets EV Care rely on a single call.
"""

from ev_contracts import (
    ManagerVerifyFailureReason,
    ManagerVerifyRequest,
    ManagerVerifyResponse,
    OwnershipVerifyFailureReason,
    OwnershipVerifyRequest,
    OwnershipVerifyResponse,
    ServiceCenterInfo,
    VehicleSpec,
    WarrantyContract,
    normalize_national_id,
    normalize_plate,
    normalize_vin,
)
from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..service import LookupService, OwnerService, VehicleService, WarrantyService

router = APIRouter(tags=["Verification"])


@router.post(
    "/vehicles/verify-ownership",
    response_model=OwnershipVerifyResponse,
    summary="Xác thực quyền sở hữu xe (VIN + biển số + model + email + CCCD)",
)
def verify_ownership(
    payload: OwnershipVerifyRequest,
    session: Session = Depends(get_session),
) -> OwnershipVerifyResponse:
    vehicle_svc = VehicleService(session)
    owner_svc = OwnerService(session)
    warranty_svc = WarrantyService(session)

    # 1. VIN must exist.
    vehicle = vehicle_svc.get_vehicle_by_vin(normalize_vin(payload.vin))
    if vehicle is None:
        return OwnershipVerifyResponse(
            verified=False,
            failure_reason=OwnershipVerifyFailureReason.VIN_NOT_FOUND,
        )

    # 2. Plate must match (normalized on both sides).
    if normalize_plate(vehicle.license_plate) != normalize_plate(payload.license_plate):
        return OwnershipVerifyResponse(
            verified=False,
            failure_reason=OwnershipVerifyFailureReason.PLATE_MISMATCH,
        )

    # 3. Declared model must match the manufacturer record.
    if vehicle.model_id != payload.model_id:
        return OwnershipVerifyResponse(
            verified=False,
            failure_reason=OwnershipVerifyFailureReason.MODEL_MISMATCH,
        )

    # 4. Owner identity: email is the primary key, national id the 2nd factor.
    owner = owner_svc.get_owner(vehicle.current_owner_id)
    if owner is None or owner.email.strip().lower() != payload.email.strip().lower():
        return OwnershipVerifyResponse(
            verified=False,
            failure_reason=OwnershipVerifyFailureReason.OWNER_EMAIL_MISMATCH,
        )
    if normalize_national_id(owner.national_id) != normalize_national_id(payload.national_id):
        return OwnershipVerifyResponse(
            verified=False,
            failure_reason=OwnershipVerifyFailureReason.NATIONAL_ID_MISMATCH,
        )

    # 5. Verified — build the technical spec + warranty snapshot.
    model = vehicle.model
    spec = VehicleSpec(
        external_vehicle_id=vehicle.vehicle_id,
        external_owner_id=owner.owner_id,
        external_model_id=vehicle.model_id,
        model_name=model.model_name if model else vehicle.model_id,
        trim=model.trim if model else None,
        color=vehicle.color,
        manufacture_date=vehicle.manufacture_date,
        production_year=model.production_year if model else None,
        battery_capacity_kwh=model.battery_capacity_kwh if model else None,
        motor_power_kw=model.motor_power_kw if model else None,
    )

    warranties: list[WarrantyContract] = []
    for w in warranty_svc.get_warranties_for_vehicle(vehicle.vehicle_id):
        policy = w.policy
        warranties.append(
            WarrantyContract(
                external_warranty_id=w.warranty_id,
                external_policy_id=w.policy_id,
                component=policy.component.value if policy else "unknown",
                start_date=w.start_date,
                end_date=w.end_date,
                km_limit=w.km_limit,
                duration_months=policy.duration_months if policy else None,
                terms_description=policy.terms_description if policy else None,
                status=w.status.value,
            )
        )

    return OwnershipVerifyResponse(verified=True, vehicle=spec, warranties=warranties)


@router.post(
    "/service-centers/verify-manager",
    response_model=ManagerVerifyResponse,
    summary="Xác thực người quản lý xưởng dịch vụ (email + CCCD)",
)
def verify_manager(
    payload: ManagerVerifyRequest,
    session: Session = Depends(get_session),
) -> ManagerVerifyResponse:
    """The manager email identifies exactly one service center; the national
    id is the second factor. On success the center's identity is returned so
    EV Care never has to ask the user which workshop they run."""
    center = LookupService(session).get_service_center_by_manager_email(
        payload.manager_email
    )
    if center is None:
        return ManagerVerifyResponse(
            verified=False,
            failure_reason=ManagerVerifyFailureReason.MANAGER_NOT_FOUND,
        )
    if normalize_national_id(center.manager_national_id) != normalize_national_id(
        payload.manager_national_id
    ):
        return ManagerVerifyResponse(
            verified=False,
            failure_reason=ManagerVerifyFailureReason.NATIONAL_ID_MISMATCH,
        )
    return ManagerVerifyResponse(
        verified=True,
        service_center=ServiceCenterInfo(
            center_id=center.center_id,
            name=center.name,
            region=center.region,
            type=center.type.value,
        ),
    )
