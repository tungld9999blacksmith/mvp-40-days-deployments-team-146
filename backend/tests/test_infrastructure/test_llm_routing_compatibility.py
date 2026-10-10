"""Keep deployed role settings working alongside develop's stage routing."""
import pytest

from src.agents import graph
from src.config import Settings
from src.infrastructure.llm import dependency
from src.infrastructure.llm.routing import settings_for_stage


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
