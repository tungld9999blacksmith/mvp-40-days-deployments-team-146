"""
pgvector-backed `VectorStore` over the shared `vector_embedding` table.

Uses cosine distance (`<=>`, matching the HNSW `vector_cosine_ops` index) and
reports `score = 1 - distance` so results are comparable with the Qdrant store.
Each operation runs in its own short transaction on the shared engine.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import cast, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session

from ..embedding import EmbeddingEngine
from .base import SearchResult, VectorRecord, VectorStore
from .models import VectorEmbedding


class PgVectorStore(VectorStore):
    def __init__(self, embedding_engine: EmbeddingEngine, engine) -> None:
        super().__init__(embedding_engine)
        self._db_engine = engine

    @property
    def backend_name(self) -> str:
        return "pgvector"

    def _upsert(self, collection: str, records: list[VectorRecord]) -> None:
        rows = [
            {
                "id": r.id,
                "collection": collection,
                "content": r.content,
                "metadata": r.metadata,
                "embedding": r.embedding,
                "embedding_model": r.embedding_model,
            }
            for r in records
        ]
        stmt = pg_insert(VectorEmbedding).values(rows)
        # Idempotent re-ingest: same id overwrites content/metadata/embedding.
        stmt = stmt.on_conflict_do_update(
            index_elements=[VectorEmbedding.id],
            set_={
                "collection": stmt.excluded.collection,
                "content": stmt.excluded.content,
                "metadata": stmt.excluded.metadata,
                "embedding": stmt.excluded.embedding,
                "embedding_model": stmt.excluded.embedding_model,
            },
        )
        with Session(self._db_engine) as session:
            session.execute(stmt)
            session.commit()

    def similarity_search_by_vector(
        self,
        collection: str,
        embedding: list[float],
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        distance = VectorEmbedding.embedding.cosine_distance(embedding)
        stmt = (
            select(VectorEmbedding, distance.label("distance"))
            .where(VectorEmbedding.collection == collection)
            .order_by(distance)
            .limit(k)
        )
        if where:
            stmt = stmt.where(VectorEmbedding.meta.op("@>")(cast(json.dumps(where), JSONB)))

        with Session(self._db_engine) as session:
            rows = session.exec(stmt).all()

        return [
            SearchResult(
                id=row.id,
                content=row.content,
                metadata=row.meta,
                score=1.0 - float(dist),
                embedding_model=row.embedding_model,
            )
            for row, dist in rows
        ]

    def delete(self, collection: str, ids: list[str]) -> None:
        stmt = delete(VectorEmbedding).where(
            VectorEmbedding.collection == collection, VectorEmbedding.id.in_(ids)
        )
        with Session(self._db_engine) as session:
            session.execute(stmt)
            session.commit()

    def delete_collection(self, collection: str) -> None:
        stmt = delete(VectorEmbedding).where(VectorEmbedding.collection == collection)
        with Session(self._db_engine) as session:
            session.execute(stmt)
            session.commit()

    def count(self, collection: str) -> int:
        stmt = (
            select(func.count())
            .select_from(VectorEmbedding)
            .where(VectorEmbedding.collection == collection)
        )
        with Session(self._db_engine) as session:
            return int(session.exec(stmt).one())
