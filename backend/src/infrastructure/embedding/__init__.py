"""Embedding engine — standardized, provider-agnostic text→vector interface.

- ``EmbeddingEngine``       — abstract port (sync + async, declared `dimensions`)
- provider adapters         — OpenAI / Gemini / HuggingFace / local
- ``create_embedding_engine`` / ``get_embedding_engine`` — factory + DI
- ``LangChainEmbeddings``   — adapter to `langchain_core.embeddings.Embeddings`
"""

from .base import (
    EmbeddingAuthError,
    EmbeddingDimensionMismatchError,
    EmbeddingEngine,
    EmbeddingError,
    EmbeddingInvalidRequestError,
    EmbeddingProviderUnavailableError,
    EmbeddingRateLimitError,
)
from .dependency import get_embedding_engine, get_embedding_engine_by_name
from .factory import create_embedding_engine

__all__ = [
    "EmbeddingAuthError",
    "EmbeddingDimensionMismatchError",
    "EmbeddingEngine",
    "EmbeddingError",
    "EmbeddingInvalidRequestError",
    "EmbeddingProviderUnavailableError",
    "EmbeddingRateLimitError",
    "create_embedding_engine",
    "get_embedding_engine",
    "get_embedding_engine_by_name",
]
