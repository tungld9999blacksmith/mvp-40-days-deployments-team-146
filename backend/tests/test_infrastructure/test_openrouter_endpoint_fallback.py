import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import httpx2
import openai
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from src.infrastructure.llm.base import ChatMessage, GenerationConfig, LLMRateLimitError
from src.infrastructure.llm.openai_compatible_provider import OpenAICompatibleProvider
from src.infrastructure.llm.openrouter_chat import OpenRouterChatOpenAI
from src.infrastructure.llm.openrouter_routing import next_endpoint_kwargs

ORDER = ["mistral/us", "mistral/eu"]


def limited():
    response = httpx2.Response(429, request=httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions"))
    return openai.RateLimitError("rate limited", response=response, body=None)


def test_retry_preserves_constraints_and_does_not_mutate_request():
    request = {
        "model": "same-model",
        "tools": [{"type": "function"}],
        "extra_body": {
            "provider": {
                "order": ORDER,
                "allow_fallbacks": True,
                "only": ["mistral"],
                "ignore": ["other"],
                "require_parameters": True,
            },
            "response_format": {"type": "json_object"},
        },
    }
    retry = next_endpoint_kwargs(request)
    assert retry["extra_body"]["provider"] == {
        "order": ["mistral/eu"],
        "allow_fallbacks": True,
        "only": ["mistral"],
        "ignore": ["other", "mistral/us"],
        "require_parameters": True,
    }
    assert retry["model"] == request["model"] and retry["tools"] == request["tools"]
    assert retry["extra_body"]["response_format"] == request["extra_body"]["response_format"]
    assert request["extra_body"]["provider"]["order"] == ORDER
    assert next_endpoint_kwargs(retry) is None
    request["extra_body"]["provider"]["allow_fallbacks"] = False
    assert next_endpoint_kwargs(request) is None
    assert next_endpoint_kwargs({}) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["agent", "rag"])
async def test_real_sdk_request_moves_endpoint_on_429_with_same_model_and_tools(adapter):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(429, json={"error": {"code": 429, "message": "limited"}})
        return httpx.Response(
            200,
            json={
                "id": "test-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "mistralai/mistral-small-2603",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        if adapter == "agent":
            provider = OpenRouterChatOpenAI(
                api_key="test",
                model="mistralai/mistral-small-2603",
                base_url="https://openrouter.ai/api/v1",
                http_async_client=client,
                max_retries=0,
                extra_body={"provider": {"order": ORDER, "allow_fallbacks": True}},
            )
            tool = {
                "type": "function",
                "function": {"name": "read", "description": "Read", "parameters": {"type": "object", "properties": {}}},
            }
            result = await provider.bind_tools([tool]).ainvoke([HumanMessage(content="Hi")])
            assert result.content == "OK"
            assert requests[1]["tools"] == requests[0]["tools"]
        else:
            provider = OpenAICompatibleProvider(
                api_key="test",
                model="mistralai/mistral-small-2603",
                provider_name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                default_endpoint_order=ORDER,
            )
            await provider._client.close()
            provider._client = openai.AsyncOpenAI(
                api_key="test", base_url="https://openrouter.ai/api/v1", http_client=client, max_retries=0
            )
            result = await provider.chat([ChatMessage(role="user", content="Hi")])
            assert result.text == "OK"
        assert len(requests) == 2
        assert requests[1]["model"] == requests[0]["model"]
        assert requests[1]["messages"] == requests[0]["messages"]
        assert requests[1]["provider"]["order"] == ["mistral/eu"]
        assert requests[1]["provider"]["ignore"] == ["mistral/us"]


@pytest.mark.asyncio
async def test_all_endpoints_limited_is_bounded_and_explicit_opt_out_is_respected():
    provider = OpenAICompatibleProvider(
        api_key="test", model="same", provider_name="openrouter", default_endpoint_order=ORDER
    )
    create = AsyncMock(side_effect=limited())
    provider._client.chat.completions.create = create
    with pytest.raises(LLMRateLimitError):
        await provider.chat([])
    assert create.await_count == 2
    create.reset_mock()
    with pytest.raises(LLMRateLimitError):
        await provider.chat([], GenerationConfig(extra={"extra_body": {"provider": {"allow_fallbacks": False}}}))
    assert create.await_count == 1
    await provider._client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_agent_stream_only_retries_before_any_output(monkeypatch, partial):
    calls = []

    async def stream(self, messages, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            if partial:
                yield "first"
            raise limited()
        yield "second"

    monkeypatch.setattr(ChatOpenAI, "_astream", stream)
    provider = OpenRouterChatOpenAI(
        api_key="test", model="same", max_retries=0, extra_body={"provider": {"order": ORDER}}
    )
    output = []
    if partial:
        with pytest.raises(openai.RateLimitError):
            async for chunk in provider._astream([]):
                output.append(chunk)
        assert output == ["first"] and len(calls) == 1
    else:
        assert [chunk async for chunk in provider._astream([])] == ["second"]
        assert len(calls) == 2
        assert calls[-1]["extra_body"]["provider"]["ignore"] == ["mistral/us"]


def test_sync_agent_switches_endpoint(monkeypatch):
    calls = []

    def generate(self, messages, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise limited()
        return "OK"

    monkeypatch.setattr(ChatOpenAI, "_generate", generate)
    provider = OpenRouterChatOpenAI(
        api_key="test", model="same", max_retries=0, extra_body={"provider": {"order": ORDER}}
    )
    assert provider._generate([]) == "OK"
    assert calls[-1]["extra_body"]["provider"]["order"] == ["mistral/eu"]


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_adapter_stream_does_not_repeat_partial_output_and_closes_stream(partial):
    class Stream:
        def __init__(self, fail):
            self.fail = fail
            self.close = AsyncMock()

        async def __aiter__(self):
            if not self.fail or partial:
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="OK"))])
            if self.fail:
                raise limited()

    first, second = Stream(True), Stream(False)
    provider = OpenAICompatibleProvider(
        api_key="test", model="same", provider_name="openrouter", default_endpoint_order=ORDER
    )
    create = AsyncMock(side_effect=[first, second])
    provider._client.chat.completions.create = create
    output = []
    if partial:
        with pytest.raises(LLMRateLimitError):
            async for text in provider.chat_stream([]):
                output.append(text)
        assert output == ["OK"] and create.await_count == 1
    else:
        assert [text async for text in provider.chat_stream([])] == ["OK"]
        assert create.await_count == 2
        assert create.call_args.kwargs["extra_body"]["provider"]["order"] == ["mistral/eu"]
        second.close.assert_awaited_once()
    first.close.assert_awaited_once()
    await provider._client.close()
