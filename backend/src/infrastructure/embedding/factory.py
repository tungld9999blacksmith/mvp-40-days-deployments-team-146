from __future__ import annotations

from ...config import Settings
from .base import EmbeddingEngine


def create_embedding_engine(settings: Settings, provider: str | None = None) -> EmbeddingEngine:
    """Build the EmbeddingEngine for *provider* (or `settings.embedding_provider`).

    Provider SDKs are imported lazily inside each branch so that, e.g., a
    deployment using only OpenAI never needs `sentence-transformers` installed.
    """
    name = provider or settings.embedding_provider
    dims = settings.embedding_dimensions

    if name == "openai":
        from .openai_provider import OpenAIEmbeddingEngine

        return OpenAIEmbeddingEngine(
            api_key=settings.openai_api_key,
            model=settings.embedding_openai_model,
            dimensions=dims,
        )
    if name == "gemini":
        from .gemini_provider import GeminiEmbeddingEngine

        return GeminiEmbeddingEngine(
            api_key=settings.gemini_api_key,
            model=settings.embedding_gemini_model,
            dimensions=dims,
        )
    if name == "huggingface":
        from .huggingface_provider import HuggingFaceEmbeddingEngine

        return HuggingFaceEmbeddingEngine(
            api_key=settings.huggingface_api_key,
            model=settings.embedding_huggingface_model,
            dimensions=dims,
        )
    if name == "local":
        from .local_provider import LocalEmbeddingEngine

        return LocalEmbeddingEngine(model=settings.embedding_local_model, dimensions=dims)

    raise ValueError(f"Unknown embedding provider: {name!r}")
