"""Additive forecast contract shared by HTTP, agent tools and snapshots."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class MaintenanceForecast(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: str
    quality: str | None = None
    avg_km_per_day: float | None = None
    observation_days: float | None = None
    sample_days: int | None = None
    anchor_recorded_at: datetime | None = None
    km_forecast_date: date | None = None
    official_time_due_date: date | None = None
    projected_due_date: date | None = None
    basis: str | None = None
    possibly_reached: bool = False
    reminder_recommended: bool = False
    reminder_lead_days: int | None = None
    algorithm_version: str = "usage-v1"
    calculated_at: datetime
