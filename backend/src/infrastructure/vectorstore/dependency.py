from __future__ import annotations

from functools import lru_cache

from ...config import get_settings
from ..embedding.dependency import get_embedding_engine_by_name
from .base import VectorStore
from .factory import create_vector_store


@lru_cache
def _cached_store(backend: str, embedding_provider: str) -> VectorStore:
    settings = get_settings()
    engine = get_embedding_engine_by_name(embedding_provider)
    return create_vector_store(settings, engine, backend=backend)


def get_vector_store() -> VectorStore:
    """Default store dependency — reads `settings.vector_store` and the default
    embedding provider so both are cached as one coherent pair."""
    settings = get_settings()
    return _cached_store(settings.vector_store, settings.embedding_provider)


def get_vector_store_by_name(backend: str) -> VectorStore:
    """Explicit backend selection, keyed with the default embedding provider."""
    return _cached_store(backend, get_settings().embedding_provider)


@lru_cache
def _cached_knowledge_store(backend: str, embedding_provider: str) -> VectorStore:
    if backend == "qdrant":
        from ..qdrant.dependency import get_qdrant_service
        from .qdrant_store import QdrantVectorStore

        settings = get_settings()
        return QdrantVectorStore(
            get_embedding_engine_by_name(embedding_provider),
            get_qdrant_service(settings.qdrant_url, settings.qdrant_api_key, settings.qdrant_prefer_grpc).client,
            knowledge_collection=settings.qdrant_collection_name,
        )

    from ..supabase.db import engine
    from .knowledge_store import KnowledgeVectorStore

    return KnowledgeVectorStore(get_embedding_engine_by_name(embedding_provider), engine)


def get_knowledge_vector_store() -> VectorStore:
    """Knowledge store using the selected backend and shared embedding engine."""
    settings = get_settings()
    return _cached_knowledge_store(settings.vector_store, settings.embedding_provider)
