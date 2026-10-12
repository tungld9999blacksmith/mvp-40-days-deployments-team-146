from datetime import date, datetime
from uuid import UUID

from pydantic import ConfigDict, Field, StrictBool, StrictInt, model_validator
from pydantic.alias_generators import to_camel

from src.modules.notification.schemas import CamelModel


class TripPlanIn(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    departure_date: date
    return_date: date | None = None
    distance_km: StrictInt = Field(ge=1, le=20000)
    reminder_enabled: StrictBool = False

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("Return date must not precede departure")
        return self


class TripAdvice(CamelModel):
    status: str
    reasons: list[str] = Field(default_factory=list)
    milestone_km: int | None = None
    projected_trip_end_km: float | None = None
    projected_usage_before_departure_km: float = 0
    prepare_by: date | None = None
    has_booking: bool = False
    preferred_service_window: dict | None = None
    preferred_workshop: dict | None = None
    reminder_active: bool = False


class TripPlanOut(CamelModel):
    id: UUID
    departure_date: date
    return_date: date | None = None
    distance_km: int
    reminder_enabled: bool
    updated_at: datetime
    advice: TripAdvice


class TripPlanEnvelope(CamelModel):
    data: TripPlanOut | None
