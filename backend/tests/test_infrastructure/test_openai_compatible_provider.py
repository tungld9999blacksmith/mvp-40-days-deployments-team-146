from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2
import openai
import pytest

from src.infrastructure.llm.base import ChatMessage, LLMProviderUnavailableError, LLMRateLimitError
from src.infrastructure.llm.openai_compatible_provider import OpenAICompatibleProvider


def _fake_response(text: str = "Hello!") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text),
                finish_reason="stop",
            )
        ],
        model="gpt-4o-mini",
        usage=SimpleNamespace(prompt_tokens=8, completion_tokens=3),
    )


@pytest.fixture
def provider() -> OpenAICompatibleProvider:
    p = OpenAICompatibleProvider(api_key="test-key", model="gpt-4o-mini")
    p._client.chat.completions.create = AsyncMock(return_value=_fake_response())
    return p


@pytest.mark.asyncio
async def test_chat_maps_response_fields(provider: OpenAICompatibleProvider):
    result = await provider.chat([ChatMessage(role="user", content="Hi")])

    assert result.text == "Hello!"
    assert result.model == "gpt-4o-mini"
    assert result.stop_reason == "stop"
    assert result.usage.input_tokens == 8
    assert result.usage.output_tokens == 3


@pytest.mark.asyncio
async def test_chat_keeps_system_message_inline(provider: OpenAICompatibleProvider):
    await provider.chat(
        [
            ChatMessage(role="system", content="Be terse."),
            ChatMessage(role="user", content="Hi"),
        ]
    )

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["messages"] == [
        {"role": "system", "content": "Be terse."},
        {"role": "user", "content": "Hi"},
    ]


def test_grok_and_deepseek_reuse_the_same_provider_class_with_base_url():
    grok = OpenAICompatibleProvider(
        api_key="k", model="grok-4", provider_name="grok", base_url="https://api.x.ai/v1"
    )
    deepseek = OpenAICompatibleProvider(
        api_key="k", model="deepseek-chat", provider_name="deepseek", base_url="https://api.deepseek.com"
    )
    assert grok.provider_name == "grok"
    assert deepseek.provider_name == "deepseek"


@pytest.mark.asyncio
async def test_rate_limit_error_is_translated(provider: OpenAICompatibleProvider):
    request = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx2.Response(429, request=request)
    provider._client.chat.completions.create = AsyncMock(
        side_effect=openai.RateLimitError("rate limited", response=response, body=None)
    )

    with pytest.raises(LLMRateLimitError):
        await provider.chat([ChatMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_connection_error_is_translated(provider: OpenAICompatibleProvider):
    request = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    provider._client.chat.completions.create = AsyncMock(
        side_effect=openai.APIConnectionError(request=request)
    )

    with pytest.raises(LLMProviderUnavailableError):
        await provider.chat([ChatMessage(role="user", content="Hi")])
