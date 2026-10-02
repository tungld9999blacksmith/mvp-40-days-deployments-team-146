"""
Chroma-backed `VectorStore`.

Vectors are always supplied by our `EmbeddingEngine` (collections are created
with `hnsw:space=cosine` and no server-side embedding function), so Chroma and
pgvector return comparable cosine scores.
"""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from ...config import Settings
from ..embedding import EmbeddingEngine
from .base import SearchResult, VectorRecord, VectorStore

_COSINE = {"hnsw:space": "cosine"}


class ChromaVectorStore(VectorStore):
    def __init__(self, embedding_engine: EmbeddingEngine, settings: Settings) -> None:
        super().__init__(embedding_engine)
        chroma_settings = ChromaSettings()
        if settings.chroma_user and settings.chroma_password:
            chroma_settings = ChromaSettings(
                chroma_client_auth_provider="chromadb.auth.basic_authn.BasicAuthClientProvider",
                chroma_client_auth_credentials=f"{settings.chroma_user}:{settings.chroma_password}",
            )
        self._client = chromadb.HttpClient(
            host=settings.chroma_host, port=settings.chroma_port, settings=chroma_settings
        )

    @property
    def backend_name(self) -> str:
        return "chroma"

    def _collection(self, name: str):
        return self._client.get_or_create_collection(name=name, metadata=_COSINE)

    def _upsert(self, collection: str, records: list[VectorRecord]) -> None:
        # Chroma has no dedicated column, so the model tag rides in metadata.
        metadatas = [
            {**r.metadata, "embedding_model": r.embedding_model} if r.embedding_model else dict(r.metadata)
            for r in records
        ]
        payload_metadatas = metadatas if any(metadatas) else None
        self._collection(collection).upsert(
            ids=[r.id for r in records],
            embeddings=[r.embedding for r in records],
            documents=[r.content for r in records],
            metadatas=payload_metadatas,
        )

    def similarity_search_by_vector(
        self,
        collection: str,
        embedding: list[float],
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        result = self._collection(collection).query(
            query_embeddings=[embedding],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]
        return [
            SearchResult(
                id=id_,
                content=doc or "",
                metadata=meta or {},
                # Chroma cosine distance = 1 - cosine similarity.
                score=1.0 - float(dist),
                embedding_model=(meta or {}).get("embedding_model"),
            )
            for id_, doc, meta, dist in zip(ids, documents, metadatas, distances, strict=True)
        ]

    def delete(self, collection: str, ids: list[str]) -> None:
        self._collection(collection).delete(ids=ids)

    def delete_collection(self, collection: str) -> None:
        self._client.delete_collection(name=collection)

    def count(self, collection: str) -> int:
        return self._collection(collection).count()
