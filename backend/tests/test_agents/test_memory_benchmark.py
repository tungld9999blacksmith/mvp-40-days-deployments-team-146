"""Calibration must not hide malformed answers or report unknown spend as zero."""

from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from scripts import benchmark_agent_memory as benchmark
from tests.test_agents.test_checkpoint_history import FakeChat


@pytest.mark.asyncio
async def test_usage_collector_keeps_numbers_without_response_text():
    collector = benchmark.UsageCollector()
    result = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="Sensitive response must not be retained",
                        usage_metadata={"input_tokens": 123, "output_tokens": 45, "total_tokens": 168},
                        response_metadata={"token_usage": {"cost": 0.0001}},
                    )
                )
            ]
        ]
    )
    await collector.on_llm_end(result)
    assert collector.calls == [{"input_tokens": 123, "output_tokens": 45, "provider_cost_usd": 0.0001}]
    assert "Sensitive" not in str(collector.calls)


@pytest.mark.asyncio
async def test_malformed_answers_are_evaluated_and_unknown_usage_has_no_cost(monkeypatch):
    monkeypatch.setattr(benchmark, "get_agent_llm", lambda: FakeChat(responses=["invalid JSON"] * 20))
    result = await benchmark.live_benchmark()
    assert result["evaluated"] == 20 and result["accuracy_percent"] == 0
    assert result["status"] == "completed"
    assert not result["usage_complete"] and result["token_price_estimate_usd"] is None


@pytest.mark.asyncio
async def test_rate_limit_stops_without_claiming_accuracy_or_zero_spend(monkeypatch):
    class ProviderRateLimitError(RuntimeError):
        pass

    class UnavailableGraph:
        async def ainvoke(self, *args, **kwargs):
            raise ProviderRateLimitError()

    monkeypatch.setattr(benchmark, "get_agent_llm", lambda: FakeChat(responses=["unused"]))
    builder = Mock(return_value=UnavailableGraph())
    monkeypatch.setattr(benchmark, "build_graph", builder)
    result = await benchmark.live_benchmark()
    assert result["total"] == 1 and result["evaluated"] == 0
    assert result["status"] == "blocked_provider_rate_limit"
    assert result["accuracy_percent"] is None and result["provider_cost_usd"] is None
    assert result["token_price_estimate_usd"] is None
