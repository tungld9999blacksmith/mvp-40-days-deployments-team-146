"""OEM integration module — response schemas (camelCase JSON)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WebhookAckOut(CamelModel):
    event_id: str
    accepted: bool
    duplicate: bool
    ignored: bool


class WebhookAckEnvelope(CamelModel):
    data: WebhookAckOut
