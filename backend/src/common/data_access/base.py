"""Repository port — the persistence operations every entity shares.

Services depend on this interface; ``SQLModelRepository`` is the database
implementation, and tests can swap in an in-memory fake.

Transactions: write methods only ``flush`` (so generated ids / server
defaults are available) and never commit. The caller owns the transaction
and commits once per unit of work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any, Generic, TypeVar

from .filters import FilterSpec, SortSpec
from .pagination import CursorPage, KeysetPage, OffsetPage

ModelT = TypeVar("ModelT")
IdT = TypeVar("IdT")


class Repository(ABC, Generic[ModelT, IdT]):
    # ── Create ─────────────────────────────────────────────────────────
    @abstractmethod
    def create(self, entity: ModelT | Mapping[str, Any]) -> ModelT:
        """Insert one entity (or build it from a field mapping) and return it."""

    @abstractmethod
    def create_many(self, entities: Iterable[ModelT | Mapping[str, Any]]) -> list[ModelT]:
        """Insert several entities in one flush."""

    # ── Read ───────────────────────────────────────────────────────────
    @abstractmethod
    def get(self, entity_id: IdT) -> ModelT | None:
        """Return the entity with this primary key, or ``None``."""

    @abstractmethod
    def get_or_raise(self, entity_id: IdT) -> ModelT:
        """Like ``get`` but raises ``EntityNotFoundError`` when missing."""

    @abstractmethod
    def exists(self, filters: FilterSpec = None) -> bool:
        """True when at least one row matches ``filters``."""

    @abstractmethod
    def count(self, filters: FilterSpec = None) -> int:
        """Number of rows matching ``filters``."""

    # ── Search ─────────────────────────────────────────────────────────
    @abstractmethod
    def find_by(self, field: str, value: Any, *, order_by: SortSpec = None) -> list[ModelT]:
        """All rows where ``field == value``."""

    @abstractmethod
    def find_one_by(self, field: str, value: Any) -> ModelT | None:
        """First row where ``field == value``, or ``None``."""

    @abstractmethod
    def find_in(self, field: str, values: Iterable[Any], *, order_by: SortSpec = None) -> list[ModelT]:
        """All rows where ``field`` is one of ``values`` (empty ``values`` → ``[]``)."""

    @abstractmethod
    def search(
        self,
        filters: FilterSpec = None,
        *,
        order_by: SortSpec = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ModelT]:
        """All rows matching every filter (filters are AND-ed)."""

    @abstractmethod
    def find_one(self, filters: FilterSpec = None, *, order_by: SortSpec = None) -> ModelT | None:
        """First row matching ``filters``, or ``None``."""

    # ── Update ─────────────────────────────────────────────────────────
    @abstractmethod
    def update(self, entity: ModelT, values: Mapping[str, Any]) -> ModelT:
        """Set ``values`` on an already-loaded entity. Primary keys cannot change."""

    @abstractmethod
    def update_by_id(self, entity_id: IdT, values: Mapping[str, Any]) -> ModelT:
        """Load by id then ``update``; raises ``EntityNotFoundError`` when missing."""

    # ── Delete ─────────────────────────────────────────────────────────
    @abstractmethod
    def delete(self, entity: ModelT) -> None:
        """Delete an already-loaded entity."""

    @abstractmethod
    def delete_by_id(self, entity_id: IdT) -> bool:
        """Delete by id; returns ``False`` when nothing matched."""

    # ── Pagination ─────────────────────────────────────────────────────
    @abstractmethod
    def paginate_offset(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        filters: FilterSpec = None,
        order_by: SortSpec = None,
        with_total: bool = True,
    ) -> OffsetPage[ModelT]:
        """Page-number pagination (``page`` starts at 1)."""

    @abstractmethod
    def paginate_keyset(
        self,
        *,
        limit: int = 20,
        after: Mapping[str, Any] | None = None,
        filters: FilterSpec = None,
        order_by: SortSpec = None,
    ) -> KeysetPage[ModelT]:
        """Rows strictly after the sort-key values in ``after`` (``KeysetPage.next_key``)."""

    @abstractmethod
    def paginate_cursor(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        filters: FilterSpec = None,
        order_by: SortSpec = None,
    ) -> CursorPage[ModelT]:
        """Bidirectional pagination with opaque ``next_cursor`` / ``prev_cursor`` tokens."""


__all__ = ["IdT", "ModelT", "Repository"]
