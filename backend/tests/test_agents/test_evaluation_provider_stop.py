"""A failed provider preflight cannot consume subsequent repeats or sessions."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.evaluation_v2 import artifacts, runner


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["OpenAIAuthenticationError: 401 User not found", "APIStatusError: 402 payment required", "RateLimitError: 429"])
async def test_provider_failure_skips_remaining_repeats_and_sessions(tmp_path, monkeypatch, error):
    monkeypatch.setattr(artifacts, "RESULTS", tmp_path)

    async def failed(case, *_):
        return {"case_id": case["id"], "category": case["category"], "trace": {"error": error, "latency_seconds": 0, "provider_cost_usd": None}, "metrics": {"task_passed": False, "safety_violations": []}}

    evaluate = AsyncMock(side_effect=failed)
    sessions = AsyncMock()
    monkeypatch.setattr(runner, "evaluate", evaluate)
    monkeypatch.setattr(runner, "evaluate_session", sessions)
    args = SimpleNamespace(dataset=artifacts.ROOT / "eval/test_cases/agent_cases_v2_1.json", category=["reminder"], case=None, limit=2,
                           model=["mistralai/mistral-small-2603"], endpoint_order=None, repeats=3, max_tokens=1536, timeout=60, delay=0,
                           baseline_runtime=None, sessions=True, run_name="provider-stop")
    assert await runner.run(args) == 2
    assert evaluate.await_count == 1
    sessions.assert_not_awaited()
    comparison = json.loads((tmp_path / "provider-stop/comparison.json").read_text(encoding="utf-8"))
    assert len(comparison) == 1 and comparison[0]["attempted"] == 1
    assert comparison[0]["selected"] == 2 and not comparison[0]["complete"]
    assert comparison[0]["remaining_repeats_skipped"] == 2
    assert comparison[0]["sessions"] == [] and comparison[0]["sessions_skipped_reason"]
    assert (tmp_path / "provider-stop/provider_stops.json").exists()


@pytest.mark.asyncio
async def test_session_error_stops_remaining_sessions_and_repeats(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RESULTS", tmp_path)

    async def passed(case, *_):
        return {"case_id": case["id"], "category": case["category"], "trace": {"error": None, "latency_seconds": 0, "provider_cost_usd": 0}, "metrics": {"task_passed": True, "safety_violations": []}}

    evaluate = AsyncMock(side_effect=passed)
    sessions = AsyncMock(return_value={"session_id": "SESSION-01", "error": "RateLimitError: 429", "write_safety_passed": True, "turns": [], "task_success": "NEEDS_HUMAN_REVIEW"})
    monkeypatch.setattr(runner, "evaluate", evaluate)
    monkeypatch.setattr(runner, "evaluate_session", sessions)
    args = SimpleNamespace(dataset=artifacts.ROOT / "eval/test_cases/agent_cases_v2_1.json", category=["reminder"], case=None, limit=1,
                           model=["mistralai/mistral-small-2603"], endpoint_order=None, repeats=3, max_tokens=1536, timeout=60, delay=0,
                           baseline_runtime=None, sessions=True, run_name="session-stop")
    assert await runner.run(args) == 2
    assert evaluate.await_count == sessions.await_count == 1
    result = json.loads((tmp_path / "session-stop/comparison.json").read_text(encoding="utf-8"))[0]
    assert result["sessions_attempted"] == 1 and result["sessions_selected"] == 20
    assert result["remaining_repeats_skipped"] == 2
    assert result["sessions_skipped_reason"] == "PROVIDER_OR_RUNTIME_ERROR_IN_SESSION"
