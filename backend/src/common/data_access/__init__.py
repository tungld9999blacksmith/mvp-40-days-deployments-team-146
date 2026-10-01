"""Generic, entity-agnostic data access (repository pattern).

- ``Repository``          — abstract port (CRUD, search, 3 pagination styles)
- ``SQLModelRepository``  — SQLModel implementation; subclass and set ``model``
- ``filters``             — ``Filter`` / ``SortField`` value objects + helpers
- ``pagination``          — ``OffsetPage`` / ``KeysetPage`` / ``CursorPage``
"""

from .base import Repository
from .errors import (
    DataAccessError,
    EntityNotFoundError,
    InvalidCursorError,
    InvalidPageRequestError,
    UnknownFieldError,
)
from .filters import (
    Filter,
    FilterSpec,
    Op,
    SortField,
    SortSpec,
    eq,
    ge,
    gt,
    ilike,
    in_,
    is_not_null,
    is_null,
    le,
    like,
    lt,
    ne,
    not_in,
)
from .pagination import CursorPage, KeysetPage, OffsetPage
from .sqlmodel_repository import SQLModelRepository

__all__ = [
    "CursorPage",
    "DataAccessError",
    "EntityNotFoundError",
    "Filter",
    "FilterSpec",
    "InvalidCursorError",
    "InvalidPageRequestError",
    "KeysetPage",
    "OffsetPage",
    "Op",
    "Repository",
    "SQLModelRepository",
    "SortField",
    "SortSpec",
    "UnknownFieldError",
    "eq",
    "ge",
    "gt",
    "ilike",
    "in_",
    "is_not_null",
    "is_null",
    "le",
    "like",
    "lt",
    "ne",
    "not_in",
]
