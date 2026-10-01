"""API endpoints: Warranty (policy, contract, claim)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..service import VehicleService, WarrantyService

router = APIRouter(tags=["Warranty"])


@router.get(
    "/warranty-policies/{model_id}",
    summary="Chính sách bảo hành theo model (tất cả component)",
)
def get_warranty_policies(
    model_id: str,
    session: Session = Depends(get_session),
):
    svc = WarrantyService(session)
    policies = svc.get_policies_by_model(model_id)
    if not policies:
        raise HTTPException(404, f"No warranty policies for model {model_id}")
    return [
        {
            "policy_id": p.policy_id,
            "model_id": p.model_id,
            "component": p.component.value,
            "duration_months": p.duration_months,
            "km_limit": p.km_limit,
            "terms_description": p.terms_description,
        }
        for p in policies
    ]


@router.get(
    "/vehicles/{vehicle_id}/warranties",
    summary="Hợp đồng bảo hành của xe (instance theo component)",
)
def get_vehicle_warranties(
    vehicle_id: str,
    session: Session = Depends(get_session),
):
    # Kiểm tra xe tồn tại
    v_svc = VehicleService(session)
    if not v_svc.get_vehicle(vehicle_id):
        raise HTTPException(404, f"Vehicle {vehicle_id} not found")

    svc = WarrantyService(session)
    warranties = svc.get_warranties_for_vehicle(vehicle_id)
    return [
        {
            "warranty_id": w.warranty_id,
            "vehicle_id": w.vehicle_id,
            "policy_id": w.policy_id,
            "start_date": str(w.start_date),
            "end_date": str(w.end_date),
            "km_limit": w.km_limit,
            "status": w.status.value,
        }
        for w in warranties
    ]


@router.get(
    "/vehicles/{vehicle_id}/warranty-claims",
    summary="Lịch sử yêu cầu bảo hành (approved/rejected/pending)",
)
def get_warranty_claims(
    vehicle_id: str,
    session: Session = Depends(get_session),
):
    v_svc = VehicleService(session)
    if not v_svc.get_vehicle(vehicle_id):
        raise HTTPException(404, f"Vehicle {vehicle_id} not found")

    svc = WarrantyService(session)
    claims = svc.get_claims_for_vehicle(vehicle_id)
    return [
        {
            "claim_id": c.claim_id,
            "vehicle_id": c.vehicle_id,
            "warranty_id": c.warranty_id,
            "claim_date": str(c.claim_date),
            "status": c.status.value,
            "reject_reason": c.reject_reason,
        }
        for c in claims
    ]


@router.get(
    "/warranty-claims/{claim_id}",
    summary="Chi tiết 1 yêu cầu bảo hành (kèm lý do từ chối nếu có)",
)
def get_claim_detail(
    claim_id: str,
    session: Session = Depends(get_session),
):
    svc = WarrantyService(session)
    claim = svc.get_claim(claim_id)
    if not claim:
        raise HTTPException(404, f"Claim {claim_id} not found")

    result: dict = {
        "claim_id": claim.claim_id,
        "vehicle_id": claim.vehicle_id,
        "warranty_id": claim.warranty_id,
        "claim_date": str(claim.claim_date),
        "status": claim.status.value,
        "reject_reason": claim.reject_reason,
    }

    # Kèm thông tin warranty policy để AI giải thích được
    if claim.warranty and claim.warranty.policy:
        policy = claim.warranty.policy
        result["warranty_detail"] = {
            "component": policy.component.value,
            "duration_months": policy.duration_months,
            "km_limit": policy.km_limit,
            "terms_description": policy.terms_description,
            "warranty_end_date": str(claim.warranty.end_date),
            "warranty_status": claim.warranty.status.value,
        }

    return result
