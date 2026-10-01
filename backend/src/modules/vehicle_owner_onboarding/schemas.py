"""Onboarding module — request/response schemas (camelCase JSON).

All API payloads use camelCase; responses are wrapped in a ``{"data": ...}``
envelope (see the ``*Envelope`` models). Enum-like fields are typed as ``str``
and carry UPPER_SNAKE_CASE values produced by the service (``enum.name``).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model: accept/emit camelCase, still allow snake_case on input."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        # Fields like ``model_id`` / ``model_name`` are domain terms here,
        # not Pydantic's protected ``model_`` namespace.
        protected_namespaces=(),
    )


# ===========================================================================
# Shared output blocks
# ===========================================================================
class OnboardingStateOut(CamelModel):
    status: str
    next_step: str
    profile_completed: bool
    profile_completed_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None


class UserSummaryOut(CamelModel):
    user_id: int
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    full_name: str | None = None
    account_status: str
    roles: list[str] = Field(default_factory=list)


class ProfileOut(CamelModel):
    email: str | None = None
    display_name: str | None = None
    full_name: str | None = None
    phone_number: str | None = None
    national_id_masked: str | None = None
    date_of_birth: date | None = None


class LocationOut(CamelModel):
    location_type: str
    address_line: str
    ward: str | None = None
    district: str | None = None
    province: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    source: str


class VehicleSpecOut(CamelModel):
    model_id: str | None = None
    model_name: str | None = None
    trim: str | None = None
    color: str | None = None
    manufacture_date: date | None = None
    production_year: int | None = None
    battery_capacity_kwh: Decimal | None = None
    motor_power_kw: Decimal | None = None


class VehicleOut(CamelModel):
    vehicle_id: UUID
    vin: str
    license_plate: str
    declared_model_id: str
    verification_status: str
    verification_failure_reason: str | None = None
    verified_at: datetime | None = None
    spec: VehicleSpecOut | None = None


class WarrantyOut(CamelModel):
    component: str
    start_date: date
    end_date: date
    km_limit: int | None = None
    duration_months: int | None = None
    status: str
    terms_description: str | None = None


class ConsentStateOut(CamelModel):
    granted: bool
    policy_version: str


class LatestVerificationOut(CamelModel):
    attempt_id: UUID
    status: str
    failure_reason: str | None = None
    requested_at: datetime
    responded_at: datetime | None = None


class VerificationResultOut(CamelModel):
    attempt_id: UUID
    status: str
    failure_reason: str | None = None
    message: str
    remaining_attempts: int


class VehicleModelOut(CamelModel):
    model_id: str
    model_name: str
    trim: str | None = None
    production_year: int | None = None


# ===========================================================================
# Requests
# ===========================================================================
class ConsentIn(CamelModel):
    granted: bool
    policy_version: str = Field(..., max_length=20)


class LocationIn(CamelModel):
    address_line: str = Field(..., min_length=5, max_length=500)
    ward: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    province: str = Field(..., min_length=1, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    source: str = Field(default="MANUAL")
    place_id: str | None = Field(default=None, max_length=255)


class ProfileUpdateRequest(CamelModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    phone_number: str = Field(..., min_length=8, max_length=20)
    national_id: str = Field(..., min_length=9, max_length=20)
    date_of_birth: date | None = None
    location: LocationIn
    personal_data_consent: ConsentIn


class VehicleVerificationRequest(CamelModel):
    vin: str = Field(..., min_length=1, max_length=32)
    license_plate: str = Field(..., min_length=1, max_length=20)
    model_id: str = Field(..., min_length=1, max_length=64)
    manufacture_year: int | None = Field(default=None, ge=2000, le=2100)
    oem_data_sharing_consent: ConsentIn


# ===========================================================================
# Endpoint data + envelopes
# ===========================================================================
class SignInData(CamelModel):
    is_new_user: bool
    user: UserSummaryOut
    onboarding: OnboardingStateOut


class OnboardingData(CamelModel):
    onboarding: OnboardingStateOut
    profile: ProfileOut
    location: LocationOut | None = None
    vehicle: VehicleOut | None = None
    warranties: list[WarrantyOut] = Field(default_factory=list)
    latest_verification: LatestVerificationOut | None = None
    remaining_attempts: int
    consents: dict[str, ConsentStateOut | None] = Field(default_factory=dict)


class ProfileUpdateData(CamelModel):
    onboarding: OnboardingStateOut
    profile: ProfileOut
    location: LocationOut


class VehicleModelsData(CamelModel):
    items: list[VehicleModelOut]


class VerificationData(CamelModel):
    onboarding: OnboardingStateOut
    verification: VerificationResultOut
    vehicle: VehicleOut
    warranties: list[WarrantyOut] = Field(default_factory=list)


class SignInEnvelope(CamelModel):
    data: SignInData


class OnboardingEnvelope(CamelModel):
    data: OnboardingData


class ProfileUpdateEnvelope(CamelModel):
    data: ProfileUpdateData


class VehicleModelsEnvelope(CamelModel):
    data: VehicleModelsData


class VerificationEnvelope(CamelModel):
    data: VerificationData
