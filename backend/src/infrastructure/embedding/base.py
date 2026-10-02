"""
Embedding engine abstraction — standardizes text→vector calls across
OpenAI, Gemini, Hugging Face and local models behind a single interface.

Rules (same discipline as infrastructure/llm/base.py):
    - This file has NO dependency on any provider SDK.
    - Concrete engines (openai_provider.py, etc.) implement `EmbeddingEngine`
      and are the only files allowed to import a provider SDK.
    - Callers depend on `EmbeddingEngine` + the error hierarchy below, never on
      a concrete engine class or a provider's own exception types.

LangChain/LangGraph compatibility:
    The method names (`embed_documents`, `embed_query`, `aembed_documents`,
    `aembed_query`) intentionally match `langchain_core.embeddings.Embeddings`,
    so `langchain_adapter.LangChainEmbeddings` is a thin, dependency-free wrapper
    that any LangChain retriever / vector store can consume.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Errors — engines must translate their SDK's exceptions into these.
# ---------------------------------------------------------------------------
class EmbeddingError(Exception):
    """Base exception for all embedding engine errors."""


class EmbeddingAuthError(EmbeddingError):
    """Invalid or missing API key/credentials."""


class EmbeddingRateLimitError(EmbeddingError):
    """Provider rate limit was hit."""


class EmbeddingInvalidRequestError(EmbeddingError):
    """Request was rejected by the provider (bad params, invalid model, ...)."""


class EmbeddingProviderUnavailableError(EmbeddingError):
    """Network error or provider-side outage (5xx, timeout, connection error)."""


class EmbeddingDimensionMismatchError(EmbeddingError):
    """A returned vector's length did not match the engine's declared `dimensions`."""


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class EmbeddingEngine(ABC):
    """
    Standardized interface every concrete embedding engine must implement.

    Both sync and async variants are required: repositories/vector stores in
    this codebase are synchronous, while LangGraph nodes and the realtime path
    are async. Concrete engines implement whichever is native and bridge the
    other (async SDK → run in a thread; sync-only → offload with a threadpool).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable identifier, e.g. "openai", "gemini", "huggingface", "local"."""

    @property
    @abstractmethod
    def model(self) -> str:
        """The concrete model id this engine embeds with."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """
        Fixed output vector length. Callers (and pgvector columns) rely on this
        being constant for a given engine instance.
        """

    @property
    def identity(self) -> str:
        """Stable "<provider>:<model>" tag stored next to every vector, so a
        row always records which model produced it (vectors of different models
        must never be compared, even at the same dimension)."""
        return f"{self.provider_name}:{self.model}"

    # -- sync -------------------------------------------------------------
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents; result[i] corresponds to texts[i]."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""

    # -- async ------------------------------------------------------------
    @abstractmethod
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Async variant of `embed_documents`."""

    @abstractmethod
    async def aembed_query(self, text: str) -> list[float]:
        """Async variant of `embed_query`."""

    # -- shared validation helper ----------------------------------------
    def _validate(self, vectors: list[list[float]]) -> list[list[float]]:
        """Guard against silent dimension drift between config and provider."""
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingDimensionMismatchError(
                    f"{self.provider_name}:{self.model} returned a {len(vector)}-dim vector, expected {self.dimensions}"
                )
        return vectors
