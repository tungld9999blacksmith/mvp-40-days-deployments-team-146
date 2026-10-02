"""
Local embedding engine backed by `sentence-transformers` (runs on-device, no
network / API key). The dependency is optional: it is imported lazily so the
rest of the embedding package works without it installed.

    pip install sentence-transformers

Encoding is CPU/GPU-bound, so the async methods offload to a worker thread
rather than blocking the event loop.
"""

from __future__ import annotations

import anyio

from .base import EmbeddingEngine, EmbeddingInvalidRequestError


class LocalEmbeddingEngine(EmbeddingEngine):
    def __init__(self, model: str, dimensions: int, *, device: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise EmbeddingInvalidRequestError(
                "LocalEmbeddingEngine requires the optional 'sentence-transformers' "
                "package. Install it with: pip install sentence-transformers"
            ) from exc

        self._model_id = model
        self._dimensions = dimensions
        self._model = SentenceTransformer(model, device=device)

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def model(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).tolist()
        return self._validate(vectors)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await anyio.to_thread.run_sync(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> list[float]:
        return (await self.aembed_documents([text]))[0]
