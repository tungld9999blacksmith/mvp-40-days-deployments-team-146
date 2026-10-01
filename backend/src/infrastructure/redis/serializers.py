"""
Pluggable value serializers.

Every Redis structure in this package stores raw bytes; a `Serializer[T]` turns a
Python value into bytes and back. The default for typed structures is
`TypeAdapterSerializer`, which round-trips anything pydantic understands
(BaseModel / SQLModel, dataclasses, list[Model], dict, datetime, UUID, ...).
"""

from __future__ import annotations

import json
import pickle
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from .errors import SerializationError

T = TypeVar("T")


class Serializer(ABC, Generic[T]):
    @abstractmethod
    def dumps(self, value: T) -> bytes: ...

    @abstractmethod
    def loads(self, data: bytes) -> T: ...


class StrSerializer(Serializer[str]):
    def dumps(self, value: str) -> bytes:
        return str(value).encode()

    def loads(self, data: bytes) -> str:
        return data.decode() if isinstance(data, bytes) else str(data)


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    # datetime, UUID, Decimal, set, dataclass, ... — let pydantic handle the rest.
    return TypeAdapter(type(value)).dump_python(value, mode="json")


class JsonSerializer(Serializer[Any]):
    """Untyped JSON. `loads` returns plain dict/list/scalars (pydantic models come back as dicts)."""

    def __init__(self, sort_keys: bool = True) -> None:
        self._sort_keys = sort_keys

    def dumps(self, value: Any) -> bytes:
        try:
            return json.dumps(value, default=_json_default, sort_keys=self._sort_keys, separators=(",", ":")).encode()
        except (TypeError, ValueError) as exc:
            raise SerializationError(f"Cannot JSON-encode {type(value).__name__}: {exc}") from exc

    def loads(self, data: bytes) -> Any:
        try:
            return json.loads(data)
        except (TypeError, ValueError) as exc:
            raise SerializationError(f"Invalid JSON payload: {exc}") from exc


class TypeAdapterSerializer(Serializer[T]):
    """Typed JSON via pydantic: `TypeAdapterSerializer(list[Vehicle])` returns `list[Vehicle]` on loads."""

    def __init__(self, type_: type[T] | Any) -> None:
        self.type_ = type_
        self._adapter: TypeAdapter[T] = TypeAdapter(type_)

    def dumps(self, value: T) -> bytes:
        try:
            return self._adapter.dump_json(value)
        except Exception as exc:  # pydantic raises PydanticSerializationError / TypeError
            raise SerializationError(f"Cannot encode value as {self.type_!r}: {exc}") from exc

    def loads(self, data: bytes) -> T:
        try:
            return self._adapter.validate_json(data)
        except ValidationError as exc:
            raise SerializationError(f"Cached payload does not match {self.type_!r}: {exc}") from exc


class PickleSerializer(Serializer[Any]):
    """Arbitrary Python objects. Only use for data your own services wrote — never untrusted input."""

    def __init__(self, protocol: int = pickle.HIGHEST_PROTOCOL) -> None:
        self._protocol = protocol

    def dumps(self, value: Any) -> bytes:
        try:
            return pickle.dumps(value, protocol=self._protocol)
        except (pickle.PicklingError, TypeError, AttributeError) as exc:
            raise SerializationError(f"Cannot pickle {type(value).__name__}: {exc}") from exc

    def loads(self, data: bytes) -> Any:
        try:
            return pickle.loads(data)  # noqa: S301 — trusted, self-written data only
        except Exception as exc:
            raise SerializationError(f"Cannot unpickle payload: {exc}") from exc


def serializer_for(type_: Any | None) -> Serializer[Any]:
    """Pick a sensible default serializer for a type hint (None / Any -> untyped JSON)."""
    if type_ is None or type_ is Any:
        return JsonSerializer()
    if type_ is str:
        return StrSerializer()
    return TypeAdapterSerializer(type_)
