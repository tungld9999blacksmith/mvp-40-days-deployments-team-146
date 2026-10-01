"""Shared contracts (Pydantic schemas) for the EV manufacturer system API.

These models are the wire contract between the mock EV system
(`mock-ev-system`) and the EV Care backend. Keeping them in one shared
package guarantees both sides serialize/deserialize the exact same shape and
apply identical normalization when matching VIN / license plates.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Normalization helpers (shared so both sides compare values identically)
# ---------------------------------------------------------------------------
def normalize_vin(vin: str) -> str:
    """Uppercase and strip a VIN for storage and comparison."""
    return vin.strip().upper()


def normalize_plate(plate: str) -> str:
    """Normalize a license plate: uppercase, drop spaces, dots and dashes.

    Example: ``29A-123.45`` -> ``29A12345``. Both the manufacturer record and
    the user-supplied value must go through this before being compared.
    """
    return re.sub(r"[\s.\-]", "", plate).upper()


def normalize_national_id(national_id: str) -> str:
    """Keep digits only from a national id (CCCD)."""
    return re.sub(r"\D", "", national_id)


# ---------------------------------------------------------------------------
# Vehicle ownership verification (POST /vehicles/verify-ownership)
# ---------------------------------------------------------------------------
class OwnershipVerifyFailureReason(str, Enum):
    """Reasons the manufacturer rejects an ownership verification request."""

    VIN_NOT_FOUND = "VIN_NOT_FOUND"
    PLATE_MISMATCH = "PLATE_MISMATCH"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    OWNER_EMAIL_MISMATCH = "OWNER_EMAIL_MISMATCH"
    NATIONAL_ID_MISMATCH = "NATIONAL_ID_MISMATCH"


class OwnershipVerifyRequest(BaseModel):
    """What EV Care sends to the manufacturer to prove a user owns a vehicle.

    Ownership is proven when the VIN exists and the plate + model + owner
    email + owner national id all match the manufacturer record.
    """

    vin: str = Field(..., description="Vehicle Identification Number")
    license_plate: str = Field(..., description="License plate as typed by the user")
    model_id: str = Field(..., description="Model id the user selected")
    email: str = Field(..., description="Google account email used to sign in")
    national_id: str = Field(..., description="Citizen id (CCCD) entered at onboarding")


class WarrantyContract(BaseModel):
    """A single warranty contract for one vehicle component."""

    external_warranty_id: str
    external_policy_id: str | None = None
    component: str
    start_date: date
    end_date: date
    km_limit: int | None = None
    duration_months: int | None = None
    terms_description: str | None = None
    status: str


class VehicleSpec(BaseModel):
    """Technical snapshot of a vehicle as known by the manufacturer."""

    external_vehicle_id: str
    external_owner_id: str
    external_model_id: str
    model_name: str
    trim: str | None = None
    color: str | None = None
    manufacture_date: date | None = None
    production_year: int | None = None
    battery_capacity_kwh: float | None = None
    motor_power_kw: float | None = None


class OwnershipVerifyResponse(BaseModel):
    """Result of an ownership verification.

    On success ``verified`` is True and ``vehicle`` + ``warranties`` are set.
    On failure ``verified`` is False and ``failure_reason`` explains why.
    """

    verified: bool
    failure_reason: OwnershipVerifyFailureReason | None = None
    vehicle: VehicleSpec | None = None
    warranties: list[WarrantyContract] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Service-center manager verification (POST /service-centers/verify-manager)
# ---------------------------------------------------------------------------
class ManagerVerifyFailureReason(str, Enum):
    """Reasons the manufacturer rejects a workshop-manager verification."""

    MANAGER_NOT_FOUND = "MANAGER_NOT_FOUND"
    NATIONAL_ID_MISMATCH = "NATIONAL_ID_MISMATCH"


class ManagerVerifyRequest(BaseModel):
    """What EV Care sends to prove a user manages a service center.

    The manufacturer keeps one (manager email, national id) pair per service
    center; a manager email maps to exactly one center.
    """

    manager_email: str = Field(..., description="Google account email used to sign in")
    manager_national_id: str = Field(..., description="Citizen id (CCCD) entered at onboarding")


class ServiceCenterInfo(BaseModel):
    """Public identity of a service center as known by the manufacturer."""

    center_id: str
    name: str
    region: str
    type: str


class ManagerVerifyResponse(BaseModel):
    """Result of a manager verification.

    On success ``verified`` is True and ``service_center`` is the center that
    the manager identity is registered for. On failure ``failure_reason`` is set.
    """

    verified: bool
    failure_reason: ManagerVerifyFailureReason | None = None
    service_center: ServiceCenterInfo | None = None


# ---------------------------------------------------------------------------
# Webhooks: manufacturer -> EV Care (POST /api/v1/integrations/oem/webhooks)
# ---------------------------------------------------------------------------
WEBHOOK_EVENT_ID_HEADER = "X-OEM-Event-Id"
WEBHOOK_TIMESTAMP_HEADER = "X-OEM-Timestamp"
WEBHOOK_SIGNATURE_HEADER = "X-OEM-Signature"
WEBHOOK_SIGNATURE_PREFIX = "sha256="


class WebhookEventType(str, Enum):
    """Signals the manufacturer sends when a vehicle's data changed.

    The webhook is only a signal: the receiver re-reads the manufacturer API
    (usage / service-history) instead of trusting the payload.
    """

    VEHICLE_USAGE_UPDATED = "vehicle.usage.updated"
    VEHICLE_SERVICE_HISTORY_UPDATED = "vehicle.service_history.updated"


class WebhookEvent(BaseModel):
    """Body of a manufacturer webhook call."""

    event_type: WebhookEventType = Field(..., alias="eventType")
    vehicle_id: str = Field(..., alias="vehicleId", max_length=64)
    occurred_at: datetime = Field(..., alias="occurredAt")

    model_config = {"populate_by_name": True}


def sign_webhook(secret: str, timestamp: int | str, raw_body: bytes) -> str:
    """Return the ``X-OEM-Signature`` value for a webhook body.

    Signature = ``sha256=`` + hex(HMAC-SHA256(secret, "{timestamp}.{raw_body}")).
    """
    message = f"{timestamp}.".encode() + raw_body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return WEBHOOK_SIGNATURE_PREFIX + digest


def verify_webhook_signature(
    secret: str, timestamp: int | str, raw_body: bytes, signature: str
) -> bool:
    """Constant-time check of an ``X-OEM-Signature`` header."""
    return hmac.compare_digest(sign_webhook(secret, timestamp, raw_body), signature)


__all__ = [
    "normalize_vin",
    "normalize_plate",
    "normalize_national_id",
    "OwnershipVerifyFailureReason",
    "OwnershipVerifyRequest",
    "WarrantyContract",
    "VehicleSpec",
    "OwnershipVerifyResponse",
    "ManagerVerifyFailureReason",
    "ManagerVerifyRequest",
    "ServiceCenterInfo",
    "ManagerVerifyResponse",
    "WEBHOOK_EVENT_ID_HEADER",
    "WEBHOOK_TIMESTAMP_HEADER",
    "WEBHOOK_SIGNATURE_HEADER",
    "WEBHOOK_SIGNATURE_PREFIX",
    "WebhookEventType",
    "WebhookEvent",
    "sign_webhook",
    "verify_webhook_signature",
]
