"""Errors raised by the generic data-access layer."""

from __future__ import annotations


class DataAccessError(Exception):
    """Base class for every error raised by ``src.common.data_access``."""


class EntityNotFoundError(DataAccessError):
    def __init__(self, model_name: str, entity_id: object) -> None:
        super().__init__(f"{model_name} with id={entity_id!r} not found")
        self.model_name = model_name
        self.entity_id = entity_id


class UnknownFieldError(DataAccessError, ValueError):
    """A filter / sort / update referenced a field that is not a mapped column."""

    def __init__(self, model_name: str, field: str) -> None:
        super().__init__(f"{model_name} has no column {field!r}")
        self.model_name = model_name
        self.field = field


class InvalidPageRequestError(DataAccessError, ValueError):
    """Bad page number / page size / keyset values."""


class InvalidCursorError(DataAccessError, ValueError):
    """The cursor is malformed, tampered with, or was issued for another sort order."""
