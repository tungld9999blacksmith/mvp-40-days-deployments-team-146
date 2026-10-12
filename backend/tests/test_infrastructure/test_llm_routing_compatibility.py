"""Keep deployed role settings working alongside develop's stage routing."""
import os

import pytest

from src.agents import graph
from src.config import Settings
from src.infrastructure.llm import dependency
from src.infrastructure.llm.routing import settings_for_stage


@pytest.fixture(autouse=True)
def isolate_llm_environment(monkeypatch):
    # Settings(_env_file=None) still reads process variables populated by dotenv.
    for name in list(os.environ):
        if name.startswith(("LLM_", "OPENROUTER_", "GEMINI_", "GOOGLE_")) or name == "MODEL_NAME":
            monkeypatch.delenv(name)


@pytest.fixture
def configured(monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_provider="openrouter",
        openrouter_api_key="test-key",
        openrouter_model="shared-model",
        openrouter_agent_model="legacy-agent",
        openrouter_rewrite_model="legacy-rewrite",
        openrouter_rag_model="legacy-rag",
        openrouter_write_model="reserved-write",
        openrouter_agent_endpoint_order="mistral/us",
        llm_orchestrator_provider="",
        llm_orchestrator_model="",
        llm_rewrite_provider="",
        llm_rewrite_model="",
        llm_rag_provider="",
        llm_rag_model="",
        llm_booking_provider="",
        llm_booking_model="",
        llm_booking_check_enabled=False,
        llm_fallback_provider="",
    )
    dependency.get_llm_provider_for_stage.cache_clear()
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    yield settings
    dependency.get_llm_provider_for_stage.cache_clear()


def test_agent_alias_and_orchestrator_share_deployed_model_and_route(configured):
    agent = dependency.get_llm_provider_for_stage("agent")
    assert agent is dependency.get_llm_provider_for_stage("orchestrator")
    assert agent._model == "legacy-agent"
    assert agent._default_endpoint_order == ["mistral/us"]


def test_explicit_stage_override_wins_in_both_graph_and_provider(configured):
    configured.llm_orchestrator_model = "explicit-agent"
    assert graph.get_agent_llm().model_name == "explicit-agent"
    assert dependency.get_llm_provider_for_stage("agent")._model == "explicit-agent"
    assert configured.openrouter_agent_model == "legacy-agent"


def test_booking_does_not_activate_reserved_write_model(configured):
    assert not configured.llm_booking_check_enabled
    assert settings_for_stage(configured, "booking").openrouter_model == "shared-model"
    assert dependency.get_llm_provider_for_stage("write")._model == "reserved-write"
    configured.llm_booking_model = "explicit-reviewer"
    assert dependency.get_llm_provider_for_stage("booking")._model == "explicit-reviewer"


def test_model_change_does_not_reuse_an_unresolved_stage_cache(configured):
    old = dependency.get_llm_provider_for_stage("rag")
    configured.llm_rag_model = "new-rag"
    new = dependency.get_llm_provider_for_stage("rag")
    assert new is not old and new._model == "new-rag"
    assert configured.openrouter_model == "shared-model"


@pytest.mark.asyncio
async def test_booking_reviewer_loads_own_route_and_retries_429(tmp_path, monkeypatch):
    import json

    import httpx
    import openai
    from langchain_core.messages import AIMessage, HumanMessage

    from src.agents import tool_review

    monkeypatch.delenv("OPENROUTER_WRITE_ENDPOINT_ORDER", raising=False)
    env = tmp_path / "reviewer.env"
    env.write_text("OPENROUTER_WRITE_ENDPOINT_ORDER=mistral/us,mistral/eu\n", encoding="utf-8")
    settings = Settings(
        _env_file=env,
        llm_provider="openrouter",
        openrouter_api_key="test-key",
        llm_booking_check_enabled=True,
        llm_booking_provider="openrouter",
        llm_booking_model="mistralai/mistral-small-2603",
        openrouter_agent_endpoint_order="unrelated-agent-endpoint",
    )
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    monkeypatch.setattr(tool_review, "get_settings", lambda: settings)
    dependency.get_llm_provider_for_stage.cache_clear()
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(429, json={"error": {"code": 429, "message": "limited"}})
        return httpx.Response(200, json={
            "id": "review-completion", "object": "chat.completion", "created": 1,
            "model": settings.llm_booking_model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"allowed":true}'},
                         "finish_reason": "stop"}],
        })

    provider = dependency.get_llm_provider_for_stage("booking")
    await provider._client.close()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider._client = openai.AsyncOpenAI(
            api_key="test-key", base_url="https://openrouter.ai/api/v1", http_client=client, max_retries=0,
        )
        try:
            assert await tool_review.review_tool_call(
                [HumanMessage(content="Tắt riêng email"), AIMessage(content="")],
                {"name": "update_reminder_settings", "args": {"email_enabled": False}},
            ) is True
            assert len(requests) == 2
            assert requests[0]["provider"]["order"] == ["mistral/us", "mistral/eu"]
            assert requests[1]["provider"]["order"] == ["mistral/eu"]
            assert requests[1]["provider"]["ignore"] == ["mistral/us"]
            assert requests[1]["model"] == requests[0]["model"] == settings.llm_booking_model
            assert requests[1]["messages"] == requests[0]["messages"]
            assert settings.openrouter_endpoints_for_stage("agent") == ("unrelated-agent-endpoint",)
        finally:
            await provider._client.close()
            dependency.get_llm_provider_for_stage.cache_clear()
