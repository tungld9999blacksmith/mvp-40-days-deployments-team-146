"""Vector store — one provider-agnostic interface over Qdrant and pgvector.

- ``VectorStore``            — abstract port (add / similarity_search / admin)
- ``VectorRecord`` / ``SearchResult`` — I/O value objects
- ``QdrantVectorStore`` / ``ChromaVectorStore`` / ``PgVectorStore`` — backends (cosine, engine-embedded)
- ``create_vector_store`` / ``get_vector_store`` — factory + DI
"""

from .base import SearchResult, VectorError, VectorRecord, VectorStore
from .dependency import (
    get_knowledge_vector_store,
    get_vector_store,
    get_vector_store_by_name,
)
from .factory import create_vector_store
from .knowledge_store import KNOWLEDGE_ALL
from .record_policy import (
    CONVERSATION_MESSAGES,
    VectorMetadataPolicy,
    VectorRecordBuilder,
    mask_pii,
    policy_for,
)

__all__ = [
    "CONVERSATION_MESSAGES",
    "KNOWLEDGE_ALL",
    "SearchResult",
    "VectorError",
    "VectorMetadataPolicy",
    "VectorRecord",
    "VectorRecordBuilder",
    "VectorStore",
    "create_vector_store",
    "get_knowledge_vector_store",
    "get_vector_store",
    "get_vector_store_by_name",
    "mask_pii",
    "policy_for",
]
