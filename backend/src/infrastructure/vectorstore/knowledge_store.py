"""
`VectorStore` adapter over the existing ``document_chunk`` table (ENT-407).

This unifies knowledge RAG with the rest of the app: retrieval and ingestion go
through the same `VectorStore` interface and the same `EmbeddingEngine` as chat
messages, while keeping ``document_chunk``'s dedicated schema, its unique
``(document_id, chunk_index)`` constraint, the ``maintenance_rule_source``
evidence FK, and its HNSW cosine index untouched.

Namespace mapping — ``collection`` is the document:
    - writes / delete / count with ``collection = str(document_id)`` scope to
      one document. Re-ingesting a document is delete_collection + add
      (BR-ENT-409: re-ingest replaces all of a document's chunks).
    - search with ``collection = KNOWLEDGE_ALL`` ("*") ranks across every
      document; any other value scopes the search to that document.

``document_chunk`` stores no per-row model tag (BR-ENT-410: every chunk uses the
same 1024-dim model), so ``SearchResult.embedding_model`` is left ``None`` here.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlmodel import Session

from ...common.core.knowledge import DocumentChunk
from ..embedding import EmbeddingEngine
from .base import SearchResult, VectorRecord, VectorStore

KNOWLEDGE_ALL = "*"


class KnowledgeVectorStore(VectorStore):
    def __init__(self, embedding_engine: EmbeddingEngine, engine) -> None:
        super().__init__(embedding_engine)
        self._db_engine = engine

    @property
    def backend_name(self) -> str:
        return "pgvector-document-chunk"

    def _upsert(self, collection: str, records: list[VectorRecord]) -> None:
        if collection == KNOWLEDGE_ALL:
            raise ValueError("add() needs a concrete document_id as `collection`, not '*'")
        document_id = UUID(collection)
        with Session(self._db_engine) as session:
            for order, record in enumerate(records):
                chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_index=record.metadata.get("chunk_index", order),
                    content=record.content,
                    page_number=record.metadata.get("page_number"),
                    embedding=record.embedding,
                )
                session.add(chunk)
            session.commit()

    def similarity_search_by_vector(
        self,
        collection: str,
        embedding: list[float],
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        distance = DocumentChunk.embedding.cosine_distance(embedding)
        stmt = select(DocumentChunk, distance.label("distance")).order_by(distance).limit(k)
        if collection != KNOWLEDGE_ALL:
            stmt = stmt.where(DocumentChunk.document_id == UUID(collection))
        if where and where.get("document_id"):
            stmt = stmt.where(DocumentChunk.document_id == UUID(str(where["document_id"])))

        with Session(self._db_engine) as session:
            rows = session.exec(stmt).all()

        return [
            SearchResult(
                id=str(chunk.id),
                content=chunk.content,
                metadata={
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                },
                score=1.0 - float(dist),
            )
            for chunk, dist in rows
        ]

    def delete(self, collection: str, ids: list[str]) -> None:
        stmt = delete(DocumentChunk).where(DocumentChunk.id.in_([UUID(i) for i in ids]))
        with Session(self._db_engine) as session:
            session.execute(stmt)
            session.commit()

    def delete_collection(self, collection: str) -> None:
        """Delete every chunk of a document (the re-ingest replace step)."""
        if collection == KNOWLEDGE_ALL:
            raise ValueError("refusing to delete every document; pass a concrete document_id")
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == UUID(collection))
        with Session(self._db_engine) as session:
            session.execute(stmt)
            session.commit()

    def count(self, collection: str) -> int:
        stmt = select(func.count()).select_from(DocumentChunk)
        if collection != KNOWLEDGE_ALL:
            stmt = stmt.where(DocumentChunk.document_id == UUID(collection))
        with Session(self._db_engine) as session:
            return int(session.exec(stmt).one())
