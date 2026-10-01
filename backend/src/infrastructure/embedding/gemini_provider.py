"""
Embedding engine backed by Google Gemini (`google-genai` SDK).

`gemini-embedding-001` supports `output_dimensionality` to match the codebase's
configured vector size. Google returns non-normalized vectors when the output
dimension is reduced below the model's native 3072, so those are L2-normalized
here to keep cosine distance well-behaved in the vector store.
"""

from __future__ import annotations

import math

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from .base import (
    EmbeddingAuthError,
    EmbeddingEngine,
    EmbeddingInvalidRequestError,
    EmbeddingProviderUnavailableError,
    EmbeddingRateLimitError,
)

_NATIVE_DIM = 3072


class GeminiEmbeddingEngine(EmbeddingEngine):
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dimensions = dimensions

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _config(self, task_type: str) -> genai_types.EmbedContentConfig:
        return genai_types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self._dimensions,
        )

    def _extract(self, response) -> list[list[float]]:
        vectors = [list(embedding.values) for embedding in response.embeddings]
        if self._dimensions != _NATIVE_DIM:
            vectors = [_normalize(v) for v in vectors]
        return self._validate(vectors)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.models.embed_content(
                model=self._model, contents=texts, config=self._config("RETRIEVAL_DOCUMENT")
            )
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return self._extract(response)

    def embed_query(self, text: str) -> list[float]:
        try:
            response = self._client.models.embed_content(
                model=self._model, contents=[text], config=self._config("RETRIEVAL_QUERY")
            )
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return self._extract(response)[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.aio.models.embed_content(
                model=self._model, contents=texts, config=self._config("RETRIEVAL_DOCUMENT")
            )
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return self._extract(response)

    async def aembed_query(self, text: str) -> list[float]:
        try:
            response = await self._client.aio.models.embed_content(
                model=self._model, contents=[text], config=self._config("RETRIEVAL_QUERY")
            )
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return self._extract(response)[0]


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        if code in (401, 403):
            return EmbeddingAuthError(str(exc))
        if code == 429:
            return EmbeddingRateLimitError(str(exc))
        if code is not None and code >= 500:
            return EmbeddingProviderUnavailableError(str(exc))
        return EmbeddingInvalidRequestError(str(exc))
    return exc
