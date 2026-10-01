"""Workshop-owner auth — response schemas (camelCase)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class OnboardingStateOut(CamelModel):
    status: str
    next_step: str
    profile_completed: bool
    profile_completed_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None


class SessionData(CamelModel):
    owner_id: UUID
    email: str
    account_status: str
    onboarding: OnboardingStateOut
    last_login_at: datetime | None = None
    last_logout_at: datetime | None = None


class SessionEnvelope(CamelModel):
    data: SessionData
