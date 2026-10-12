"""Demo account module — request / response DTOs (camelCase at the API edge)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DemoSessionData(CamelModel):
    custom_token: str


class DemoSessionEnvelope(CamelModel):
    data: DemoSessionData
