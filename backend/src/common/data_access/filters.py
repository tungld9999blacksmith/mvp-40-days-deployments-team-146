"""Field filters and sort specifications (model-agnostic value objects).

Filters are plain data; the repository turns them into SQL after checking the
field against the model's mapped columns, so they are safe to build from
request parameters.

    repo.search(filters=[eq("status", "active"), in_("region", ["HN", "HCM"])])
    repo.search(filters={"status": "active"})          # shorthand for eq(...)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeAlias


class Op(StrEnum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    IN = "in"
    NOT_IN = "not_in"
    LIKE = "like"
    ILIKE = "ilike"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


@dataclass(frozen=True, slots=True)
class Filter:
    field: str
    op: Op = Op.EQ
    value: Any = None


def eq(field: str, value: Any) -> Filter:
    return Filter(field, Op.EQ, value)


def ne(field: str, value: Any) -> Filter:
    return Filter(field, Op.NE, value)


def lt(field: str, value: Any) -> Filter:
    return Filter(field, Op.LT, value)


def le(field: str, value: Any) -> Filter:
    return Filter(field, Op.LE, value)


def gt(field: str, value: Any) -> Filter:
    return Filter(field, Op.GT, value)


def ge(field: str, value: Any) -> Filter:
    return Filter(field, Op.GE, value)


def in_(field: str, values: Iterable[Any]) -> Filter:
    return Filter(field, Op.IN, tuple(values))


def not_in(field: str, values: Iterable[Any]) -> Filter:
    return Filter(field, Op.NOT_IN, tuple(values))


def like(field: str, pattern: str) -> Filter:
    return Filter(field, Op.LIKE, pattern)


def ilike(field: str, pattern: str) -> Filter:
    return Filter(field, Op.ILIKE, pattern)


def is_null(field: str) -> Filter:
    return Filter(field, Op.IS_NULL)


def is_not_null(field: str) -> Filter:
    return Filter(field, Op.IS_NOT_NULL)


# ``{"status": "active"}`` is accepted wherever a filter list is, meaning eq().
FilterSpec: TypeAlias = Sequence[Filter] | Mapping[str, Any] | None


def normalize_filters(filters: FilterSpec) -> list[Filter]:
    if filters is None:
        return []
    if isinstance(filters, Mapping):
        return [eq(field, value) for field, value in filters.items()]
    return list(filters)


@dataclass(frozen=True, slots=True)
class SortField:
    field: str
    descending: bool = False

    @classmethod
    def parse(cls, spec: str) -> SortField:
        """``"created_at"`` → ascending, ``"-created_at"`` → descending."""
        spec = spec.strip()
        if spec.startswith("-"):
            return cls(spec[1:], descending=True)
        return cls(spec.lstrip("+"))


SortSpec: TypeAlias = Sequence[SortField | str] | SortField | str | None


def normalize_sort(order_by: SortSpec) -> list[SortField]:
    if order_by is None:
        return []
    if isinstance(order_by, (str, SortField)):
        order_by = [order_by]
    return [item if isinstance(item, SortField) else SortField.parse(item) for item in order_by]
