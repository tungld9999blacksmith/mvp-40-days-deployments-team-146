"""
Vector store abstraction — one interface over Qdrant and pgvector.

Design decisions that make the two backends interchangeable:
    - The `EmbeddingEngine` is the single source of truth for vectors. Both
      stores receive *precomputed* embeddings. Swapping provider or store therefore never
      silently changes which model produced the vectors.
    - Cosine is the standard metric everywhere. `SearchResult.score` is a
      similarity in [0, 1] (higher = closer), derived from each backend's
      native distance, so callers compare results the same way regardless
      of backend.
    - "collection" is the logical namespace. In Qdrant it is a collection; in
      pgvector it is the `collection` column of a shared table.

This file has NO dependency on qdrant_client or SQLAlchemy — concrete stores do.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from ..embedding import EmbeddingEngine


class VectorError(Exception):
    """Base exception for vector store errors."""


class VectorRecord(BaseModel):
    """One item to store. `embedding` is optional on input: when omitted the
    store computes it from `content` via the engine. `embedding_model` records
    which model produced the vector; when omitted `add()` fills it from the
    engine's `identity`."""

    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    embedding_model: str | None = None


class SearchResult(BaseModel):
    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Cosine similarity in [0, 1]; higher is more similar.
    score: float
    # "<provider>:<model>" that produced the stored vector.
    embedding_model: str | None = None


class VectorStore(ABC):
    """Standardized interface every concrete vector store must implement.

    Concrete stores are constructed with an `EmbeddingEngine`; the interface's
    text-based helpers delegate embedding to it, while the `*_by_vector`
    methods let callers pass vectors they already computed (e.g. in a
    LangGraph node that batched embeddings elsewhere).
    """

    def __init__(self, embedding_engine: EmbeddingEngine) -> None:
        self._engine = embedding_engine

    @property
    def embedding_engine(self) -> EmbeddingEngine:
        return self._engine

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Stable identifier, e.g. "qdrant" or "pgvector"."""

    # -- write ------------------------------------------------------------
    def add(self, collection: str, records: list[VectorRecord]) -> None:
        """Upsert records, embedding any that arrive without a vector."""
        missing = [r for r in records if r.embedding is None]
        if missing:
            vectors = self._engine.embed_documents([r.content for r in missing])
            for record, vector in zip(missing, vectors, strict=True):
                record.embedding = vector
        for record in records:
            if record.embedding_model is None:
                record.embedding_model = self._engine.identity
        self._upsert(collection, records)

    def add_texts(
        self,
        collection: str,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        metadatas = metadatas or [{} for _ in texts]
        records = [VectorRecord(id=i, content=t, metadata=m) for i, t, m in zip(ids, texts, metadatas, strict=True)]
        self.add(collection, records)

    @abstractmethod
    def _upsert(self, collection: str, records: list[VectorRecord]) -> None:
        """Backend write of records that all carry an embedding."""

    # -- search -----------------------------------------------------------
    def similarity_search(
        self,
        collection: str,
        query: str,
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        return self.similarity_search_by_vector(collection, self._engine.embed_query(query), k=k, where=where)

    @abstractmethod
    def similarity_search_by_vector(
        self,
        collection: str,
        embedding: list[float],
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Nearest `k` records to `embedding` (optionally metadata-filtered)."""

    async def asimilarity_search(
        self,
        collection: str,
        query: str,
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Async query path for LangGraph nodes: async-embed, then search."""
        embedding = await self._engine.aembed_query(query)
        return self.similarity_search_by_vector(collection, embedding, k=k, where=where)

    # -- admin ------------------------------------------------------------
    @abstractmethod
    def delete(self, collection: str, ids: list[str]) -> None: ...

    @abstractmethod
    def delete_collection(self, collection: str) -> None: ...

    @abstractmethod
    def count(self, collection: str) -> int: ...
