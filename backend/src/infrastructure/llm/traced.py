"""Tracing for LLM calls made outside LangChain (RAG rewrite / generate, booking review, follow-up).

LangSmith gets an ``llm`` run with the messages, the answer and the token usage
(cost is computed by LangSmith from model pricing). Grafana gets a thin
``chat <model>`` span: provider, model, status — no text, no tokens.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from src.infrastructure.observability import step

from .base import ChatMessage, GenerationConfig, LLMProvider, LLMResponse


def _model_of(provider: LLMProvider) -> str:
    return str(getattr(provider, "_model", None) or getattr(provider, "model", None) or "unknown")


def _usage(response: LLMResponse) -> dict[str, int]:
    usage = response.usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.input_tokens + usage.output_tokens,
    }


def _finish(current: Any, response: LLMResponse) -> LLMResponse:
    current.set(**{"gen_ai.response.model": response.model, "gen_ai.response.finish_reason": response.stop_reason})
    current.outputs(
        {"choices": [{"message": {"role": "assistant", "content": response.text}}]},
        usage=_usage(response),
    )
    return response


class TracedLLMProvider(LLMProvider):
    """Transparent wrapper: same interface and attributes as the wrapped provider."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        # Only reached for attributes the wrapper does not define (e.g. ``_model``).
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Writes reach the real provider (e.g. swapping ``_client``), never the wrapper.
        if name == "_inner":
            object.__setattr__(self, name, value)
        else:
            setattr(self._inner, name, value)

    @property
    def inner(self) -> LLMProvider:
        return self._inner

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    def _step(self, messages: list[ChatMessage], config: GenerationConfig | None, *, stream: bool):
        model = _model_of(self._inner)
        return step(
            f"chat {model}",
            run_type="llm",
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.system": self.provider_name,
                "gen_ai.request.model": model,
                "llm.stream": stream,
            },
            inputs={"messages": [m.model_dump() for m in messages]},
            metadata={
                "ls_provider": self.provider_name,
                "ls_model_name": model,
                "ls_temperature": config.temperature if config else None,
                "ls_max_tokens": config.max_tokens if config else None,
            },
        )

    async def generate_text(self, prompt: str, config: GenerationConfig | None = None) -> LLMResponse:
        with self._step([ChatMessage(role="user", content=prompt)], config, stream=False) as current:
            return _finish(current, await self._inner.generate_text(prompt, config))

    async def chat(self, messages: list[ChatMessage], config: GenerationConfig | None = None) -> LLMResponse:
        with self._step(messages, config, stream=False) as current:
            return _finish(current, await self._inner.chat(messages, config))

    async def chat_stream(
        self, messages: list[ChatMessage], config: GenerationConfig | None = None
    ) -> AsyncIterator[str]:
        with self._step(messages, config, stream=True) as current:
            chunks: list[str] = []
            async for chunk in self._inner.chat_stream(messages, config):
                chunks.append(chunk)
                yield chunk
            current.outputs({"choices": [{"message": {"role": "assistant", "content": "".join(chunks)}}]})


def traced(provider: LLMProvider) -> LLMProvider:
    """Wrap once; already-traced providers are returned unchanged."""
    return provider if isinstance(provider, TracedLLMProvider) else TracedLLMProvider(provider)
