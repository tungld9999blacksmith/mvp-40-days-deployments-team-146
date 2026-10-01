"""Generic SQLModel/SQLAlchemy implementation of ``Repository``.

Bind it to a table model by subclassing:

    class WorkshopRepository(SQLModelRepository[Workshop, UUID]):
        model = Workshop
        default_order_by = ("-created_at",)

    repo = WorkshopRepository(session)
    repo.find_in("region", ["HN", "HCM"])
    repo.paginate_cursor(limit=20, cursor=token, filters={"status": "active"})

Every field name coming from callers (filters, sort, update values, keyset
keys) is checked against the model's mapped columns, so request parameters
can be passed through without exposing arbitrary attributes.

Keyset / cursor pagination:
    - The primary key is always appended to the sort order as a tie-breaker,
      so the order is total and no row is skipped or repeated.
    - Sort columns must be NOT NULL (``NULL`` breaks row-value comparisons).
    - ``has_previous`` on a forward page (and ``has_next`` on a backward page)
      is inferred from the cursor, not re-queried.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, ClassVar, Generic

from sqlalchemy import and_, false, func, or_, true
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import InstrumentedAttribute, Mapper
from sqlalchemy.sql import ColumnElement
from sqlmodel import Session, SQLModel, select
from sqlmodel.sql.expression import SelectOfScalar

from .base import IdT, ModelT, Repository
from .errors import EntityNotFoundError, InvalidCursorError, InvalidPageRequestError, UnknownFieldError
from .filters import Filter, FilterSpec, Op, SortField, SortSpec, normalize_filters, normalize_sort
from .pagination import (
    Cursor,
    CursorPage,
    Direction,
    KeysetPage,
    OffsetPage,
    decode_cursor,
    encode_cursor,
    sort_fingerprint,
)


class SQLModelRepository(Repository[ModelT, IdT], Generic[ModelT, IdT]):
    model: type[ModelT]
    # Applied when a caller passes no ``order_by`` (the primary key is always appended).
    default_order_by: ClassVar[SortSpec] = None
    max_page_size: ClassVar[int] = 100

    def __init__(self, session: Session) -> None:
        model = getattr(type(self), "model", None)
        if not (isinstance(model, type) and issubclass(model, SQLModel)):
            raise TypeError(f"{type(self).__name__} must set `model` to a SQLModel table class")
        self._session = session
        self._mapper: Mapper = sa_inspect(model)
        self._pk_names: tuple[str, ...] = tuple(
            self._mapper.get_property_by_column(column).key for column in self._mapper.primary_key
        )

    @property
    def session(self) -> Session:
        return self._session

    # ── Create ─────────────────────────────────────────────────────────

    def create(self, entity: ModelT | Mapping[str, Any]) -> ModelT:
        instance = self._to_instance(entity)
        self._session.add(instance)
        self._session.flush()
        self._session.refresh(instance)
        return instance

    def create_many(self, entities: Iterable[ModelT | Mapping[str, Any]]) -> list[ModelT]:
        instances = [self._to_instance(entity) for entity in entities]
        if not instances:
            return []
        self._session.add_all(instances)
        self._session.flush()
        for instance in instances:
            self._session.refresh(instance)
        return instances

    # ── Read ───────────────────────────────────────────────────────────

    def get(self, entity_id: IdT) -> ModelT | None:
        return self._session.get(self.model, entity_id)

    def get_or_raise(self, entity_id: IdT) -> ModelT:
        entity = self.get(entity_id)
        if entity is None:
            raise EntityNotFoundError(self.model.__name__, entity_id)
        return entity

    def exists(self, filters: FilterSpec = None) -> bool:
        stmt = self._apply_filters(self._base_query(), filters).limit(1)
        return self._session.exec(stmt).first() is not None

    def count(self, filters: FilterSpec = None) -> int:
        subquery = self._apply_filters(self._base_query(), filters).subquery()
        return self._session.exec(select(func.count()).select_from(subquery)).one()

    # ── Search ─────────────────────────────────────────────────────────

    def find_by(self, field: str, value: Any, *, order_by: SortSpec = None) -> list[ModelT]:
        return self.search([Filter(field, Op.EQ, value)], order_by=order_by)

    def find_one_by(self, field: str, value: Any) -> ModelT | None:
        return self.find_one([Filter(field, Op.EQ, value)])

    def find_in(self, field: str, values: Iterable[Any], *, order_by: SortSpec = None) -> list[ModelT]:
        values = tuple(values)
        if not values:
            self._column(field)  # still reject unknown fields
            return []
        return self.search([Filter(field, Op.IN, values)], order_by=order_by)

    def search(
        self,
        filters: FilterSpec = None,
        *,
        order_by: SortSpec = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ModelT]:
        stmt = self._apply_filters(self._base_query(), filters)
        stmt = stmt.order_by(*self._order_clauses(self._resolve_sort(order_by)))
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return list(self._session.exec(stmt).all())

    def find_one(self, filters: FilterSpec = None, *, order_by: SortSpec = None) -> ModelT | None:
        stmt = self._apply_filters(self._base_query(), filters)
        stmt = stmt.order_by(*self._order_clauses(self._resolve_sort(order_by))).limit(1)
        return self._session.exec(stmt).first()

    # ── Update ─────────────────────────────────────────────────────────

    def update(self, entity: ModelT, values: Mapping[str, Any]) -> ModelT:
        for field, value in values.items():
            self._column(field)
            if field in self._pk_names:
                raise ValueError(f"Primary key {field!r} of {self.model.__name__} cannot be updated")
            setattr(entity, field, value)
        self._session.add(entity)
        self._session.flush()
        self._session.refresh(entity)
        return entity

    def update_by_id(self, entity_id: IdT, values: Mapping[str, Any]) -> ModelT:
        return self.update(self.get_or_raise(entity_id), values)

    # ── Delete ─────────────────────────────────────────────────────────

    def delete(self, entity: ModelT) -> None:
        self._session.delete(entity)
        self._session.flush()

    def delete_by_id(self, entity_id: IdT) -> bool:
        entity = self.get(entity_id)
        if entity is None:
            return False
        self.delete(entity)
        return True

    # ── Pagination ─────────────────────────────────────────────────────

    def paginate_offset(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        filters: FilterSpec = None,
        order_by: SortSpec = None,
        with_total: bool = True,
    ) -> OffsetPage[ModelT]:
        if page < 1:
            raise InvalidPageRequestError("page must be >= 1")
        self._check_limit(page_size)
        items = self.search(filters, order_by=order_by, limit=page_size, offset=(page - 1) * page_size)
        total = self.count(filters) if with_total else None
        return OffsetPage(items=items, page=page, page_size=page_size, total=total)

    def paginate_keyset(
        self,
        *,
        limit: int = 20,
        after: Mapping[str, Any] | None = None,
        filters: FilterSpec = None,
        order_by: SortSpec = None,
    ) -> KeysetPage[ModelT]:
        self._check_limit(limit)
        sort = self._resolve_keyset_sort(order_by)
        if after is not None:
            self._check_key_values(sort, after, InvalidPageRequestError)
        rows, has_more = self._fetch_keyset(sort, after, reverse=False, limit=limit, filters=filters)
        next_key = self._key_of(rows[-1], sort) if has_more else None
        return KeysetPage(items=rows, limit=limit, has_next=has_more, next_key=next_key)

    def paginate_cursor(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        filters: FilterSpec = None,
        order_by: SortSpec = None,
    ) -> CursorPage[ModelT]:
        self._check_limit(limit)
        sort = self._resolve_keyset_sort(order_by)
        fingerprint = sort_fingerprint([(item.field, item.descending) for item in sort])

        decoded: Cursor | None = None
        if cursor:
            decoded = decode_cursor(cursor)
            if decoded.sort_key != fingerprint:
                raise InvalidCursorError("Cursor was issued for a different sort order")
            self._check_key_values(sort, decoded.values, InvalidCursorError)

        backward = decoded is not None and decoded.direction == "prev"
        rows, has_more = self._fetch_keyset(
            sort, decoded.values if decoded else None, reverse=backward, limit=limit, filters=filters
        )
        if backward:
            rows.reverse()

        if decoded is None:
            has_next, has_previous = has_more, False
        elif backward:
            has_next, has_previous = True, has_more
        else:
            has_next, has_previous = has_more, True

        def make(anchor_row: ModelT | None, direction: Direction) -> str:
            # An empty page (rows removed since the cursor was issued) anchors
            # on the incoming cursor position so the client can turn back.
            values = self._key_of(anchor_row, sort) if anchor_row is not None else decoded.values
            return encode_cursor(Cursor(values=values, direction=direction, sort_key=fingerprint))

        next_cursor = make(rows[-1] if rows else None, "next") if has_next else None
        prev_cursor = make(rows[0] if rows else None, "prev") if has_previous else None
        return CursorPage(
            items=rows,
            limit=limit,
            has_next=has_next,
            has_previous=has_previous,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

    # ── Extension points ───────────────────────────────────────────────

    def _base_query(self) -> SelectOfScalar[ModelT]:
        """Starting ``SELECT`` for every read; override to add default scoping."""
        return select(self.model)

    # ── Internals ──────────────────────────────────────────────────────

    def _to_instance(self, entity: ModelT | Mapping[str, Any]) -> ModelT:
        if isinstance(entity, self.model):
            return entity
        if isinstance(entity, Mapping):
            for field in entity:
                self._column(field)
            return self.model(**entity)
        raise TypeError(f"Expected {self.model.__name__} or a mapping, got {type(entity).__name__}")

    def _column(self, field: str) -> InstrumentedAttribute:
        if field not in self._mapper.column_attrs:
            raise UnknownFieldError(self.model.__name__, field)
        return getattr(self.model, field)

    def _apply_filters(self, stmt: SelectOfScalar[ModelT], filters: FilterSpec) -> SelectOfScalar[ModelT]:
        clauses = [self._filter_clause(item) for item in normalize_filters(filters)]
        return stmt.where(*clauses) if clauses else stmt

    def _filter_clause(self, item: Filter) -> ColumnElement[bool]:
        column = self._column(item.field)
        value = item.value
        match Op(item.op):
            case Op.EQ:
                return column.is_(None) if value is None else column == value
            case Op.NE:
                return column.is_not(None) if value is None else column != value
            case Op.LT:
                return column < value
            case Op.LE:
                return column <= value
            case Op.GT:
                return column > value
            case Op.GE:
                return column >= value
            case Op.IN:
                values = tuple(value or ())
                return column.in_(values) if values else false()
            case Op.NOT_IN:
                values = tuple(value or ())
                return column.not_in(values) if values else true()
            case Op.LIKE:
                return column.like(value)
            case Op.ILIKE:
                return column.ilike(value)
            case Op.IS_NULL:
                return column.is_(None)
            case Op.IS_NOT_NULL:
                return column.is_not(None)
        raise ValueError(f"Unsupported filter operator {item.op!r}")

    def _resolve_sort(self, order_by: SortSpec) -> list[SortField]:
        """Requested (or default) sort, with the primary key appended as tie-breaker."""
        sort = normalize_sort(order_by if order_by is not None else self.default_order_by)
        for item in sort:
            self._column(item.field)
        seen = {item.field for item in sort}
        sort.extend(SortField(name) for name in self._pk_names if name not in seen)
        return sort

    def _resolve_keyset_sort(self, order_by: SortSpec) -> list[SortField]:
        sort = self._resolve_sort(order_by)
        for item in sort:
            if self._mapper.columns[item.field].nullable:
                raise InvalidPageRequestError(
                    f"Column {item.field!r} is nullable and cannot be used for keyset/cursor pagination"
                )
        return sort

    def _order_clauses(self, sort: Sequence[SortField], *, reverse: bool = False) -> list[ColumnElement[Any]]:
        clauses = []
        for item in sort:
            column = self._column(item.field)
            clauses.append(column.desc() if item.descending != reverse else column.asc())
        return clauses

    def _seek_clause(
        self, sort: Sequence[SortField], values: Mapping[str, Any], *, reverse: bool
    ) -> ColumnElement[bool]:
        """Rows strictly after ``values`` in ``sort`` order (before, when ``reverse``).

        Expanded as ``(a > x) OR (a = x AND b > y) OR ...`` so each column may
        have its own direction.
        """
        branches = []
        for index, item in enumerate(sort):
            conditions = [self._column(prev.field) == values[prev.field] for prev in sort[:index]]
            column = self._column(item.field)
            descending = item.descending != reverse
            conditions.append(column < values[item.field] if descending else column > values[item.field])
            branches.append(and_(*conditions))
        return or_(*branches)

    def _fetch_keyset(
        self,
        sort: Sequence[SortField],
        after: Mapping[str, Any] | None,
        *,
        reverse: bool,
        limit: int,
        filters: FilterSpec,
    ) -> tuple[list[ModelT], bool]:
        stmt = self._apply_filters(self._base_query(), filters)
        if after is not None:
            stmt = stmt.where(self._seek_clause(sort, after, reverse=reverse))
        stmt = stmt.order_by(*self._order_clauses(sort, reverse=reverse)).limit(limit + 1)
        rows = list(self._session.exec(stmt).all())
        return rows[:limit], len(rows) > limit

    def _key_of(self, entity: ModelT, sort: Sequence[SortField]) -> dict[str, Any]:
        return {item.field: getattr(entity, item.field) for item in sort}

    @staticmethod
    def _check_key_values(sort: Sequence[SortField], values: Mapping[str, Any], error: type[Exception]) -> None:
        expected = {item.field for item in sort}
        if set(values) != expected:
            raise error(f"Key values must contain exactly: {sorted(expected)}")
        if any(value is None for value in values.values()):
            raise error("Key values cannot be null")

    def _check_limit(self, limit: int) -> None:
        if not 1 <= limit <= self.max_page_size:
            raise InvalidPageRequestError(f"page size must be between 1 and {self.max_page_size}")
