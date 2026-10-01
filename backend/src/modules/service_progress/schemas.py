"""Service progress — request/response schemas (us-057 §3, §4.1)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class StageIn(str, Enum):
    SERVICING = "SERVICING"
    WAITING_PARTS = "WAITING_PARTS"
    QUALITY_CHECK = "QUALITY_CHECK"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"


class StageAny(str, Enum):
    CHECKED_IN = "CHECKED_IN"
    INSPECTING = "INSPECTING"
    SERVICING = "SERVICING"
    WAITING_PARTS = "WAITING_PARTS"
    QUALITY_CHECK = "QUALITY_CHECK"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"


class AppendProgressRequest(CamelModel):
    stage: StageIn
    note: str | None = Field(default=None, max_length=500)
    # ``null`` when the timeline is still empty.
    expected_current_stage: StageAny | None


class ProgressEntryOut(CamelModel):
    stage: str
    note: str | None
    actor_type: str
    created_at: datetime


class ProgressOut(CamelModel):
    booking_id: UUID
    booking_status: str
    current_stage: str | None
    is_frozen: bool
    next_stages: list[str] | None = None  # API-PG-01 only
    entries: list[ProgressEntryOut]


class ProgressEnvelope(CamelModel):
    data: ProgressOut
