from __future__ import annotations

from ...config import Settings
from ..embedding import EmbeddingEngine
from .base import VectorStore


def create_vector_store(
    settings: Settings,
    embedding_engine: EmbeddingEngine,
    backend: str | None = None,
) -> VectorStore:
    """Build the VectorStore for *backend* (or `settings.vector_store`).

    The store's vector dimension is defined by `embedding_engine.dimensions`;
    for pgvector it must match the `vector_embedding` column (see models.py).
    """
    name = backend or settings.vector_store

    if name == "qdrant":
        from ..qdrant.dependency import get_qdrant_service
        from .qdrant_store import QdrantVectorStore

        service = get_qdrant_service(settings.qdrant_url, settings.qdrant_api_key, settings.qdrant_prefer_grpc)
        return QdrantVectorStore(embedding_engine, service.client)
    if name == "chroma":
        from .chroma_store import ChromaVectorStore

        return ChromaVectorStore(embedding_engine, settings)
    if name == "pgvector":
        from ..supabase.db import engine
        from .pgvector_store import PgVectorStore

        return PgVectorStore(embedding_engine, engine)

    raise ValueError(f"Unknown vector store backend: {name!r}")
