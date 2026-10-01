"""Qdrant adapter for chat vectors and the existing RAG knowledge payloads."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_DNS, uuid5

from qdrant_client import QdrantClient, models

from ..embedding import EmbeddingEngine
from .base import SearchResult, VectorError, VectorRecord, VectorStore


class QdrantVectorStore(VectorStore):
    def __init__(
        self,
        embedding_engine: EmbeddingEngine,
        client: QdrantClient,
        *,
        knowledge_collection: str | None = None,
    ) -> None:
        super().__init__(embedding_engine)
        self._client = client
        self._knowledge_collection = knowledge_collection

    @property
    def backend_name(self) -> str:
        return "qdrant"

    def _name(self, collection: str) -> str:
        return self._knowledge_collection or collection

    @staticmethod
    def _point_id(record_id: str) -> str:
        # Same mapping as the RAG ingester, including non-UUID chunk IDs.
        return str(uuid5(NAMESPACE_DNS, record_id))

    def _ensure(self, collection: str, *, create: bool = False) -> bool:
        name = self._name(collection)
        if not self._client.collection_exists(name):
            if not create:
                return False
            self._client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(size=self._engine.dimensions, distance=models.Distance.COSINE),
            )
        vectors = self._client.get_collection(name).config.params.vectors
        if (
            not isinstance(vectors, models.VectorParams)
            or vectors.size != self._engine.dimensions
            or vectors.distance != models.Distance.COSINE
        ):
            raise VectorError(
                f"Qdrant collection {name!r} must use cosine vectors with "
                f"{self._engine.dimensions} dimensions; check EMBEDDING_DIMENSIONS "
                "and the embedding model. Existing data was not changed."
            )
        return True

    def _filter(self, collection: str, where: dict[str, Any] | None = None) -> models.Filter | None:
        conditions: list[models.FieldCondition] = []
        if self._knowledge_collection and collection != "*":
            conditions.append(models.FieldCondition(key="document_id", match=models.MatchValue(value=collection)))
        for key, value in (where or {}).items():
            field = (
                key
                if self._knowledge_collection
                and key in {"document_id", "model", "category", "milestone_km", "source", "page"}
                else f"metadata.{key}"
            )
            conditions.append(models.FieldCondition(key=field, match=models.MatchValue(value=value)))
        return models.Filter(must=conditions) if conditions else None

    def _upsert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        if self._knowledge_collection and collection == "*":
            raise ValueError("Pass a concrete document_id when writing knowledge")
        for record in records:
            if record.embedding is None or len(record.embedding) != self._engine.dimensions:
                raise VectorError("Record embedding dimensions do not match the engine")
        self._ensure(collection, create=True)
        name = self._name(collection)
        # Qdrant Cloud strict mode requires indexes on fields used for filtering.
        fields = {}
        if self._knowledge_collection:
            fields.update(
                {key: models.PayloadSchemaType.KEYWORD for key in ("document_id", "model", "category", "source")}
            )
            fields.update({key: models.PayloadSchemaType.INTEGER for key in ("page", "milestone_km")})
        for record in records:
            for key, value in record.metadata.items():
                kind = {
                    str: models.PayloadSchemaType.KEYWORD,
                    int: models.PayloadSchemaType.INTEGER,
                    bool: models.PayloadSchemaType.BOOL,
                }.get(type(value))
                if kind:
                    fields[f"metadata.{key}"] = kind
        schema = self._client.get_collection(name).payload_schema or {}
        for field in sorted(fields.keys() - schema.keys()):
            self._client.create_payload_index(name, field, fields[field], wait=True)
        points = []
        for record in records:
            payload = {
                "chunk_id": record.id,
                "content": record.content,
                "metadata": record.metadata,
                "embedding_model": record.embedding_model,
            }
            if self._knowledge_collection:
                payload.update(
                    {
                        "document_id": collection,
                        "page": record.metadata.get("page_number", record.metadata.get("page")),
                        "source": record.metadata.get("source", ""),
                        "model": record.metadata.get("model", "ALL"),
                        "category": record.metadata.get("category", "general"),
                        "milestone_km": record.metadata.get("milestone_km"),
                    }
                )
            points.append(models.PointStruct(id=self._point_id(record.id), vector=record.embedding, payload=payload))
        self._client.upsert(name, points, wait=True)

    def similarity_search_by_vector(
        self,
        collection: str,
        embedding: list[float],
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if k <= 0 or not self._ensure(collection):
            return []
        if len(embedding) != self._engine.dimensions:
            raise VectorError("Query embedding dimensions do not match the engine")
        hits = self._client.query_points(
            collection_name=self._name(collection),
            query=embedding,
            query_filter=self._filter(collection, where),
            limit=k,
            with_payload=True,
        ).points
        results = []
        for hit in hits:
            payload = hit.payload or {}
            metadata = dict(payload.get("metadata") or {})
            if self._knowledge_collection:
                metadata.update(
                    {
                        "document_id": payload.get("document_id"),
                        "page_number": payload.get("page", metadata.get("page_number")),
                    }
                )
            results.append(
                SearchResult(
                    id=str(payload.get("chunk_id", hit.id)),
                    content=payload.get("content", ""),
                    metadata=metadata,
                    score=float(hit.score),
                    embedding_model=payload.get("embedding_model"),
                )
            )
        return results

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids or not self._client.collection_exists(self._name(collection)):
            return
        scope = self._filter(collection)
        conditions = list(scope.must or []) if scope else []
        conditions.append(models.HasIdCondition(has_id=[self._point_id(i) for i in ids]))
        self._client.delete(self._name(collection), models.Filter(must=conditions), wait=True)

    def delete_collection(self, collection: str) -> None:
        if self._knowledge_collection and collection == "*":
            raise ValueError("Refusing to delete every document; pass a concrete document_id")
        name = self._name(collection)
        if not self._client.collection_exists(name):
            return
        if self._knowledge_collection:
            self._client.delete(name, self._filter(collection), wait=True)
        else:
            self._client.delete_collection(name)

    def count(self, collection: str) -> int:
        name = self._name(collection)
        if not self._client.collection_exists(name):
            return 0
        return self._client.count(name, count_filter=self._filter(collection), exact=True).count
