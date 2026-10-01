"""Health module — response schemas (camelCase JSON)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DependencyCheck(CamelModel):
    status: Literal["up", "down"]
    latency_ms: float
    error: str | None = None
    # Extra non-secret info, e.g. the database dialect actually in use.
    detail: str | None = None


class DependenciesHealth(CamelModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, DependencyCheck]
