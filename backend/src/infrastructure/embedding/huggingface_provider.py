"""
Embedding engine backed by the Hugging Face Inference API
(`huggingface_hub.InferenceClient` / `AsyncInferenceClient`).

Any feature-extraction model can be used (default: BAAI/bge-m3). Token-level
outputs are mean-pooled and vectors are L2-normalized so cosine distance in the
vector store behaves consistently across models.
"""

from __future__ import annotations

import math

from huggingface_hub import AsyncInferenceClient, InferenceClient
from huggingface_hub.errors import HfHubHTTPError

from .base import (
    EmbeddingAuthError,
    EmbeddingEngine,
    EmbeddingInvalidRequestError,
    EmbeddingProviderUnavailableError,
    EmbeddingRateLimitError,
)


class HuggingFaceEmbeddingEngine(EmbeddingEngine):
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self._sync = InferenceClient(model=model, token=api_key or None)
        self._async = AsyncInferenceClient(model=model, token=api_key or None)
        self._model = model
        self._dimensions = dimensions

    @property
    def provider_name(self) -> str:
        return "huggingface"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = [_pool(self._sync.feature_extraction(text)) for text in texts]
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return self._validate(vectors)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = [_pool(await self._async.feature_extraction(text)) for text in texts]
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return self._validate(vectors)

    async def aembed_query(self, text: str) -> list[float]:
        return (await self.aembed_documents([text]))[0]


def _pool(raw) -> list[float]:
    """Reduce a feature-extraction result to a single normalized vector.

    HF returns a numpy array shaped either (dim,) for sentence models or
    (tokens, dim) for token-level models; the latter is mean-pooled.
    """
    array = raw.tolist() if hasattr(raw, "tolist") else raw
    if array and isinstance(array[0], list):
        columns = len(array[0])
        pooled = [sum(row[i] for row in array) / len(array) for i in range(columns)]
    else:
        pooled = list(array)
    return _normalize(pooled)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, HfHubHTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            return EmbeddingAuthError(str(exc))
        if status == 429:
            return EmbeddingRateLimitError(str(exc))
        if status is not None and status >= 500:
            return EmbeddingProviderUnavailableError(str(exc))
        return EmbeddingInvalidRequestError(str(exc))
    return exc
