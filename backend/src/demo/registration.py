"""Registration contracts for the branch UI, backed by the shared demo store.

Verification uses the synthetic demo fixture, not a production manufacturer API.
"""

import re
from copy import deepcopy
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request

from src.modules.vehicle_owner_onboarding.schemas import ProfileUpdateRequest, VehicleVerificationRequest
from src.modules.workshop_owner_onboarding.schemas import WorkshopProfileUpdateRequest, WorkshopVerificationRequest

from .dependency import current_user
from .persistence import save_registration
from .store import DemoError
from .workshop import owner, summary

router = APIRouter(prefix="/api/v1")


def snapshot(store, account, portal="owner"):
    key = f"{portal}:{account.get('ownerId', account.get('userId'))}"
    if key not in store.onboarding:
        active = store.skip_onboarding
        store.onboarding[key] = {
            "onboarding": {
                "status": "ACTIVE" if active else "ONBOARDING_IN_PROGRESS",
                "nextStep": ("HOME" if portal == "owner" else "DASHBOARD") if active else "PROFILE",
                "profileCompleted": active,
                "profileCompletedAt": None,
                "completedAt": None,
                "expiresAt": None,
            },
            "profile": {
                "email": account["email"],
                "displayName": account.get("displayName"),
                "fullName": account.get("fullName"),
                "phoneNumber": None,
                "nationalIdMasked": None,
                "dateOfBirth": None,
            },
            "location": None,
            "vehicle": None,
            "warranties": [],
            "latestVerification": None,
            "remainingAttempts": 3,
            "consents": {},
            "registration": None,
            "latestAttempt": None,
        }
        save_registration(store)
    value = deepcopy(store.onboarding[key])
    if portal == "workshop":
        value["workshop"] = summary(store, account["workshopId"]) if value["onboarding"]["status"] == "ACTIVE" else None
    return key, value


def validate_profile(body):
    if not body.personal_data_consent.granted:
        raise DemoError("CONSENT_REQUIRED", "Cần đồng ý xử lý dữ liệu cá nhân.")
    if not re.fullmatch(r"\d{12}", body.national_id):
        raise DemoError("INVALID_FIELD_FORMAT", "CCCD phải có 12 chữ số.", field="nationalId")
    if not re.fullmatch(r"(?:0|\+84)\d{9,10}", body.phone_number):
        raise DemoError("INVALID_FIELD_FORMAT", "Số điện thoại không hợp lệ.", field="phoneNumber")


def save_profile(store, account, body, portal="owner"):
    validate_profile(body)
    key, value = snapshot(store, account, portal)
    if value["onboarding"]["status"] == "ACTIVE":
        raise DemoError("ONBOARDING_COMPLETED", "Tài khoản đã hoàn tất đăng ký.", 409)
    value["profile"].update(
        fullName=body.full_name.strip(),
        phoneNumber=body.phone_number,
        nationalIdMasked=f"********{body.national_id[-4:]}",
    )
    if portal == "owner":
        value["profile"]["dateOfBirth"] = body.date_of_birth.isoformat() if body.date_of_birth else None
        value["location"] = body.location.model_dump(mode="json", by_alias=True)
    account["fullName"] = body.full_name.strip()
    value["consents"]["personalDataProcessing"] = body.personal_data_consent.model_dump(by_alias=True)
    value["onboarding"].update(
        nextStep="VEHICLE" if portal == "owner" else "WORKSHOP",
        profileCompleted=True,
        profileCompletedAt=store.timestamp(),
    )
    store.onboarding[key] = value
    save_registration(store)
    return {"data": {k: value[k] for k in ("onboarding", "profile", "location")}}


@router.put("/onboarding/profile")
def owner_profile(body: ProfileUpdateRequest, request: Request, u=Depends(current_user)):
    return save_profile(request.app.state.services.store, u, body)


@router.put("/workshop-owner/onboarding/profile")
def workshop_profile(body: WorkshopProfileUpdateRequest, request: Request, o=Depends(owner)):
    return save_profile(request.app.state.services.store, o, body, "workshop")


@router.get("/onboarding/vehicle-models")
def vehicle_models(u=Depends(current_user)):
    return {"data": {"items": [{"modelId": "MDL-02", "modelName": "VF6", "trim": "Eco", "productionYear": 2024}]}}


def prepare_verification(store, account, body, token, portal):
    key, value = snapshot(store, account, portal)
    payload = body.model_dump(mode="json", by_alias=True)
    previous = store.onboarding_operations.get((key, token))
    if previous:
        if previous[0] != payload:
            raise DemoError("IDEMPOTENCY_CONFLICT", "Mã thao tác đã dùng với dữ liệu khác.", 409)
        return key, value, deepcopy(previous[1])
    if value["onboarding"]["status"] == "ACTIVE" or not value["onboarding"]["profileCompleted"]:
        raise DemoError("INVALID_ONBOARDING_STATE", "Hoàn tất thông tin cá nhân trước khi xác thực.", 409)
    if not body.oem_data_sharing_consent.granted:
        raise DemoError("CONSENT_REQUIRED", "Cần đồng ý chia sẻ dữ liệu để xác thực.")
    value["consents"]["oemDataSharing"] = body.oem_data_sharing_consent.model_dump(by_alias=True)
    return key, value, None


def finish(store, key, value, body, token, result):
    store.onboarding[key] = deepcopy(value)
    store.onboarding_operations[(key, token)] = (body.model_dump(mode="json", by_alias=True), deepcopy(result))
    save_registration(store)
    return result


@router.post("/onboarding/vehicle-verification")
async def verify_vehicle(
    body: VehicleVerificationRequest,
    request: Request,
    token: str = Header(alias="Idempotency-Key", min_length=1),
    u=Depends(current_user),
):
    store = request.app.state.services.store
    async with store.booking_lock:
        key, value, replay = prepare_verification(store, u, body, token, "owner")
        if replay:
            return replay
        failure = (
            "VIN_NOT_FOUND"
            if body.vin.upper() != "VF6ECO20240000001"
            else (
                "PLATE_MISMATCH"
                if re.sub(r"[^A-Z0-9]", "", body.license_plate.upper()) != "51A11111"
                else "MODEL_MISMATCH"
                if body.model_id != "MDL-02"
                else None
            )
        )
        vehicle = next(v for v in store.vehicles.values() if v["userId"] == u["userId"])
        attempt = {
            "attemptId": str(uuid4()),
            "status": "FAILED" if failure else "VERIFIED",
            "failureReason": failure,
            "message": "Thông tin không khớp xe mẫu." if failure else "Đã xác thực xe trong dữ liệu demo.",
            "remainingAttempts": max(0, value["remainingAttempts"] - bool(failure)),
        }
        if value["remainingAttempts"] == 0:
            raise DemoError("VERIFICATION_ATTEMPTS_EXCEEDED", "Đã hết lượt xác thực.", 429)
        value["remainingAttempts"] = attempt["remainingAttempts"]
        value["vehicle"] = {
            "vehicleId": vehicle["userVehicleId"],
            "vin": body.vin.upper(),
            "licensePlate": body.license_plate.upper(),
            "declaredModelId": body.model_id,
            "declaredManufactureYear": body.manufacture_year,
            "verificationStatus": attempt["status"],
            "verificationFailureReason": failure,
            "verifiedAt": None if failure else store.timestamp(),
            "spec": None if failure else {"modelId": "MDL-02", "modelName": "VF6", "trim": "Eco"},
        }
        value["latestVerification"] = {**attempt, "requestedAt": store.timestamp(), "respondedAt": store.timestamp()}
        value["onboarding"].update(
            status="VERIFICATION_FAILED" if failure else "ACTIVE",
            nextStep="VEHICLE" if failure else "HOME",
            completedAt=None if failure else store.timestamp(),
        )
        if not failure:
            vehicle.update(verified=True, active=True)
            value["warranties"] = [
                {**w, "status": "ACTIVE", "durationMonths": None, "termsDescription": None}
                for w in vehicle["warranties"]
            ]
        result = {"data": {k: value[k] for k in ("onboarding", "vehicle", "warranties")}}
        result["data"]["verification"] = attempt
        return finish(store, key, value, body, token, result)


@router.post("/workshop-owner/onboarding/workshop-verification")
async def verify_workshop(
    body: WorkshopVerificationRequest,
    request: Request,
    token: str = Header(alias="Idempotency-Key", min_length=1),
    o=Depends(owner),
):
    store = request.app.state.services.store
    async with store.booking_lock:
        key, value, replay = prepare_verification(store, o, body, token, "workshop")
        if replay:
            return replay
        if body.emergency_slots_reserved > body.total_technicians:
            raise DemoError(
                "INVALID_FIELD_FORMAT", "Chỗ dự phòng phải nhỏ hơn số kỹ thuật viên.", field="emergencySlotsReserved"
            )
        if sorted(h.day_of_week for h in body.operating_hours) != list(range(1, 8)):
            raise DemoError("INVALID_FIELD_FORMAT", "Cần đủ bảy ngày làm việc.", field="operatingHours")
        for hour in body.operating_hours:
            if not hour.is_closed and (not hour.open_time or not hour.close_time or hour.open_time >= hour.close_time):
                raise DemoError("INVALID_FIELD_FORMAT", "Giờ mở cửa phải trước giờ đóng cửa.", field="operatingHours")
        registration = body.model_dump(mode="json", by_alias=True, exclude={"oem_data_sharing_consent"})
        value["registration"] = {
            **registration,
            "registrationId": str(uuid4()),
            "verificationStatus": "VERIFIED",
            "failureReason": None,
        }
        attempt = {
            "attemptId": str(uuid4()),
            "status": "VERIFIED",
            "failureReason": None,
            "failedAttemptsLast24h": 0,
            "maxFailedAttempts": 3,
            "requestedAt": store.timestamp(),
            "respondedAt": store.timestamp(),
        }
        value["latestAttempt"] = attempt
        value["onboarding"].update(status="ACTIVE", nextStep="DASHBOARD", completedAt=store.timestamp())
        store.workshops[o["workshopId"]].update(registration)
        value["workshop"] = summary(store, o["workshopId"])
        result = {"data": {"onboarding": value["onboarding"], "verification": attempt, "workshop": value["workshop"]}}
        return finish(store, key, value, body, token, result)
