from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import httpx2
import pytest

from src.infrastructure.llm.anthropic_provider import AnthropicProvider
from src.infrastructure.llm.base import ChatMessage, LLMProviderUnavailableError, LLMRateLimitError


def _fake_response(text: str = "Hello!") -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model="claude-opus-5",
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=12, output_tokens=4),
    )


@pytest.fixture
def provider(monkeypatch) -> AnthropicProvider:
    p = AnthropicProvider(api_key="test-key", model="claude-opus-5")
    p._client.messages.create = AsyncMock(return_value=_fake_response())
    return p


@pytest.mark.asyncio
async def test_chat_maps_response_fields(provider: AnthropicProvider):
    result = await provider.chat([ChatMessage(role="user", content="Hi")])

    assert result.text == "Hello!"
    assert result.model == "claude-opus-5"
    assert result.stop_reason == "end_turn"
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 4


@pytest.mark.asyncio
async def test_chat_extracts_system_message(provider: AnthropicProvider):
    await provider.chat(
        [
            ChatMessage(role="system", content="Be terse."),
            ChatMessage(role="user", content="Hi"),
        ]
    )

    kwargs = provider._client.messages.create.call_args.kwargs
    assert kwargs["system"] == "Be terse."
    assert kwargs["messages"] == [{"role": "user", "content": "Hi"}]


@pytest.mark.asyncio
async def test_generate_text_wraps_prompt_as_user_message(provider: AnthropicProvider):
    await provider.generate_text("What is 2+2?")

    kwargs = provider._client.messages.create.call_args.kwargs
    assert kwargs["messages"] == [{"role": "user", "content": "What is 2+2?"}]


@pytest.mark.asyncio
async def test_rate_limit_error_is_translated(provider: AnthropicProvider):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(429, request=request)
    provider._client.messages.create = AsyncMock(
        side_effect=anthropic.RateLimitError("rate limited", response=response, body=None)
    )

    with pytest.raises(LLMRateLimitError):
        await provider.chat([ChatMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_connection_error_is_translated(provider: AnthropicProvider):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    provider._client.messages.create = AsyncMock(side_effect=anthropic.APIConnectionError(request=request))

    with pytest.raises(LLMProviderUnavailableError):
        await provider.chat([ChatMessage(role="user", content="Hi")])
