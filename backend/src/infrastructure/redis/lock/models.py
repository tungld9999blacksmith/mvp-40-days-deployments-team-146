from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class LockKey(BaseModel):
    """
    Identifies one piece of data to lock: `LockKey(data_type="vehicle", data_id=42)`.

    Two LockKeys with the same type + id always map to the same Redis key,
    whichever service builds them.
    """

    model_config = ConfigDict(frozen=True)

    data_type: str
    data_id: str | int | UUID

    @field_validator("data_type")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("data_type must not be empty")
        return value

    @property
    def resource(self) -> str:
        return f"{self.data_type}:{self.data_id}"

    @classmethod
    def of(cls, entity: Any, id_field: str = "id", data_type: str | None = None) -> LockKey:
        """LockKey for a model instance: `LockKey.of(vehicle)` -> vehicle:<vehicle.id>."""
        return cls(
            data_type=data_type or getattr(entity, "__tablename__", None) or type(entity).__name__,
            data_id=getattr(entity, id_field),
        )

    def __str__(self) -> str:
        return self.resource
