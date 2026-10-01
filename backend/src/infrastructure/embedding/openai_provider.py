"""
Embedding engine backed by any OpenAI `/embeddings`-compatible API.

Works for OpenAI itself and, via `base_url`, any OpenAI-compatible embedding
server. `text-embedding-3-*` models accept a `dimensions` argument, so the
engine can be pinned to the codebase's configured vector size.
"""

from __future__ import annotations

import openai

from .base import (
    EmbeddingAuthError,
    EmbeddingEngine,
    EmbeddingInvalidRequestError,
    EmbeddingProviderUnavailableError,
    EmbeddingRateLimitError,
)


class OpenAIEmbeddingEngine(EmbeddingEngine):
    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int,
        *,
        base_url: str | None = None,
        send_dimensions: bool = True,
    ) -> None:
        self._sync = openai.OpenAI(api_key=api_key, base_url=base_url)
        self._async = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._dimensions = dimensions
        # `text-embedding-3-*` supports server-side truncation to `dimensions`;
        # older models (ada-002) reject the argument, so it can be disabled.
        self._send_dimensions = send_dimensions

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _kwargs(self, texts: list[str]) -> dict:
        kwargs: dict = {"model": self._model, "input": texts}
        if self._send_dimensions:
            kwargs["dimensions"] = self._dimensions
        return kwargs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._sync.embeddings.create(**self._kwargs(texts))
        except Exception as exc:  # noqa: BLE001 — re-raised as our taxonomy
            raise _translate(exc) from exc
        return self._validate([item.embedding for item in response.data])

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._async.embeddings.create(**self._kwargs(texts))
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        return self._validate([item.embedding for item in response.data])

    async def aembed_query(self, text: str) -> list[float]:
        return (await self.aembed_documents([text]))[0]


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, openai.AuthenticationError):
        return EmbeddingAuthError(str(exc))
    if isinstance(exc, openai.RateLimitError):
        return EmbeddingRateLimitError(str(exc))
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500:
            return EmbeddingProviderUnavailableError(str(exc))
        return EmbeddingInvalidRequestError(str(exc))
    if isinstance(exc, openai.APIConnectionError):
        return EmbeddingProviderUnavailableError(str(exc))
    return exc
