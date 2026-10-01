"""Workshop-owner onboarding — request/response schemas (camelCase JSON).

Responses are wrapped in ``{"data": ...}``. Enum-like fields are ``str`` with
UPPER_SNAKE_CASE values produced by the service (``enum.name``).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ===========================================================================
# Shared output blocks
# ===========================================================================
class WorkshopOnboardingStateOut(CamelModel):
    status: str
    next_step: str
    profile_completed: bool
    profile_completed_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None


class OwnerSummaryOut(CamelModel):
    owner_id: UUID
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    full_name: str | None = None
    account_status: str
    roles: list[str] = Field(default_factory=list)


class OwnerProfileOut(CamelModel):
    email: str
    full_name: str | None = None
    phone_number: str | None = None
    national_id_masked: str | None = None


class OperatingHourOut(CamelModel):
    day_of_week: int
    is_closed: bool
    open_time: str | None = None
    close_time: str | None = None


class WorkshopSummaryOut(CamelModel):
    workshop_id: UUID
    center_id: str
    name: str
    region: str
    type: str
    status: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    hotline: str | None = None
    total_technicians: int
    emergency_slots_reserved: int
    operating_hours: list[OperatingHourOut] = Field(default_factory=list)
    onboarded_at: datetime | None = None


class RegistrationOut(CamelModel):
    registration_id: UUID
    address: str
    latitude: float | None = None
    longitude: float | None = None
    hotline: str
    total_technicians: int
    emergency_slots_reserved: int
    operating_hours: list[OperatingHourOut] = Field(default_factory=list)
    verification_status: str
    failure_reason: str | None = None


class LatestAttemptOut(CamelModel):
    attempt_id: UUID
    status: str
    failure_reason: str | None = None
    retry_count: int
    requested_at: datetime
    responded_at: datetime | None = None
    failed_attempts_last24h: int = Field(alias="failedAttemptsLast24h")
    max_failed_attempts: int


class ConsentStateOut(CamelModel):
    granted: bool
    policy_version: str


class VerificationResultOut(CamelModel):
    attempt_id: UUID
    status: str
    failure_reason: str | None = None
    failed_attempts_last24h: int = Field(alias="failedAttemptsLast24h")
    max_failed_attempts: int


# ===========================================================================
# Requests
# ===========================================================================
class ConsentIn(CamelModel):
    granted: bool
    policy_version: str = Field(..., min_length=1, max_length=20)


class WorkshopProfileUpdateRequest(CamelModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    phone_number: str = Field(..., min_length=8, max_length=20)
    national_id: str = Field(..., min_length=12, max_length=20)
    personal_data_consent: ConsentIn


class OperatingHourIn(CamelModel):
    day_of_week: int
    is_closed: bool
    open_time: str | None = None
    close_time: str | None = None


class WorkshopVerificationRequest(CamelModel):
    address: str = Field(..., min_length=5, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    hotline: str = Field(..., min_length=6, max_length=20)
    total_technicians: int = Field(..., ge=1, le=200)
    emergency_slots_reserved: int = Field(default=0, ge=0, le=200)
    operating_hours: list[OperatingHourIn]
    oem_data_sharing_consent: ConsentIn


# ===========================================================================
# Endpoint data + envelopes
# ===========================================================================
class SignInData(CamelModel):
    is_new_owner: bool
    owner: OwnerSummaryOut
    onboarding: WorkshopOnboardingStateOut
    workshop: WorkshopSummaryOut | None = None


class OnboardingData(CamelModel):
    onboarding: WorkshopOnboardingStateOut
    profile: OwnerProfileOut
    registration: RegistrationOut | None = None
    latest_attempt: LatestAttemptOut | None = None
    consents: dict[str, ConsentStateOut | None] = Field(default_factory=dict)
    workshop: WorkshopSummaryOut | None = None


class ProfileUpdateData(CamelModel):
    onboarding: WorkshopOnboardingStateOut
    profile: OwnerProfileOut


class VerificationData(CamelModel):
    onboarding: WorkshopOnboardingStateOut
    verification: VerificationResultOut
    workshop: WorkshopSummaryOut | None = None


class SignInEnvelope(CamelModel):
    data: SignInData


class OnboardingEnvelope(CamelModel):
    data: OnboardingData


class ProfileUpdateEnvelope(CamelModel):
    data: ProfileUpdateData


class VerificationEnvelope(CamelModel):
    data: VerificationData
