import json
from pathlib import Path

import pytest

from src.infrastructure.llm.base import LLMResponse
from tests.evaluation_v2.generation_replay import (
    evaluate,
    fixed_input,
    output_validity,
    probes,
    select_rows,
    validate_baseline,
)


def saved_case():
    return {"case_id": "M01", "question": "Bảo dưỡng xe VF8 gồm gì?", "expected_answer": "Kiểm tra phanh và pin.", "response": {
        "citations": [{"document_id": "doc-a", "chunk_id": "a"}],
        "metadata": {"query_analysis": {"original_query": "Bảo dưỡng xe VF8 gồm gì?", "rewritten_query": "Bảo dưỡng định kỳ VF8", "keywords": ["VF8"], "model": "VF8"},
                     "evidence_chunks": [{"doc_id": "doc-a", "chunk_id": "a", "content": "Kiểm tra phanh.", "metadata": {"title": "Manual A"}},
                                         {"doc_id": "doc-b", "chunk_id": "b", "content": "Kiểm tra pin.", "metadata": {"title": "Manual B"}}]}}}


@pytest.mark.parametrize("change", [{"fallback_required": "false"}, {"cited_doc_indexes": ["1"]}, {"confidence": "certain"}, {"unrequested": True}])
def test_schema_metric_rejects_wrong_json_types_and_unknown_fields(change):
    valid = {"answer": "Kiểm tra pin [Tài liệu 1].", "confidence": "high", "fallback_required": False, "cited_doc_indexes": [1]}
    assert output_validity(json.dumps(valid))
    assert not output_validity(json.dumps(valid | change))


def test_replay_rebuilds_all_context_before_baseline_citation_filtering():
    row = saved_case()
    item = fixed_input(row, {"model": "VF8"})
    assert [citation.document_id for citation in item["citations"]] == ["doc-a", "doc-b"]
    assert '[Tài liệu 2]' in item["context"] and "Kiểm tra pin." in item["context"]
    assert item["analysis"].rewritten_query == "Bảo dưỡng định kỳ VF8"
    assert item["vehicle"].current_odometer_km is None
    assert item["fixed_input_sha256"] == fixed_input(row, {"model": "VF8"})["fixed_input_sha256"]


@pytest.mark.asyncio
async def test_replay_detects_provider_failure_instead_of_scoring_offline_text():
    class Unavailable:
        def __init__(self):
            self.events = []
        async def chat(self, **kwargs):
            self.events.append({"error": "LLMAuthError: test transport unavailable", "latency_seconds": 0.1})
            raise RuntimeError("test transport unavailable")
    row = await evaluate(fixed_input(saved_case(), {"model": "VF8"}), Unavailable())
    assert "LLMAuthError" in row["error"]
    assert "offline summary" in row["error"]
    assert row["raw_json_schema_valid"] is None


@pytest.mark.asyncio
async def test_no_evidence_probe_refuses_without_calling_a_provider():
    class Forbidden:
        events = []
        async def chat(self, **kwargs):
            raise AssertionError("No-evidence gate must not call a model")
    item = probes(fixed_input(saved_case(), {"model": "VF8"}))[0]
    row = await evaluate(item, Forbidden())
    assert row["probe_passed"] and row["response"]["fallback_required"]
    assert row["provider_events"] == []


@pytest.mark.asyncio
async def test_replay_keeps_exact_saved_context_and_generation_budget():
    class Recorded:
        provider_name = "openrouter"
        def __init__(self):
            self.events = []
            self.kwargs = None
        async def chat(self, **kwargs):
            self.kwargs = kwargs
            raw = json.dumps({"answer": "Kiểm tra pin [Tài liệu 2].", "confidence": "high", "fallback_required": False, "cited_doc_indexes": [2]})
            self.events.append({"model": "test-model", "raw_text": raw, "stop_reason": "stop", "latency_seconds": .1, "error": None})
            return LLMResponse(text=raw, model="test-model")
    provider = Recorded()
    item = fixed_input(saved_case(), {"model": "VF8"})
    row = await evaluate(item, provider)
    assert item["context"] in provider.kwargs["messages"][1].content
    assert provider.kwargs["config"].temperature == .1 and provider.kwargs["config"].max_tokens == 3000
    assert provider.kwargs["config"].extra["response_format"]["type"] == "json_schema"
    assert provider.kwargs["config"].extra["extra_body"]["provider"]["require_parameters"] is True
    assert row["response"]["citations"][0]["document_id"] == "doc-b"
    assert row["raw_json_schema_valid"] and row["error"] is None


@pytest.mark.asyncio
async def test_provider_error_finish_reason_is_not_treated_as_a_valid_answer(monkeypatch):
    from src.config import Settings
    from tests.evaluation_v2 import rag_runner
    from tests.evaluation_v2.rag_runner import RecordedProvider

    monkeypatch.setattr(rag_runner, "get_settings", lambda: Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="test-key"))
    recorded = RecordedProvider("test-model")

    async def interrupted(**kwargs):
        return LLMResponse(model="test-model", stop_reason="error", text=json.dumps({"answer": "A valid-looking but interrupted answer", "confidence": "high", "fallback_required": False, "cited_doc_indexes": []}))

    monkeypatch.setattr(recorded.provider, "chat", interrupted)
    row = await evaluate(fixed_input(saved_case(), {"model": "VF8"}), recorded)
    assert "finish_reason=error" in row["error"]
    assert row["response"]["metadata"]["mode"] == "offline_summary"
    assert row["raw_json_schema_valid"] is None
    assert recorded.events[0]["raw_text"]  # Preserve raw response for diagnosis.


def test_actual_saved_baseline_can_be_reconstructed_without_retrieval():
    root = Path(__file__).resolve().parents[3]
    baseline = root / "eval/results/rag_v2_full_100_mistral_routed_20261007_01"
    if not baseline.exists():
        pytest.skip("Local recorded baseline is not checked into CI")
    _, rows, golden = validate_baseline(baseline, root / "backend/tests/test_agents/test_rag/evaluation/golden_set.jsonl", allow_prompt_change=True)
    assert len(rows) == 100
    assert all(fixed_input(row, golden[row["case_id"]])["context"] for row in rows)


def test_changed_prompt_requires_explicit_development_iteration():
    root = Path(__file__).resolve().parents[3]
    baseline = root / "eval/results/rag_v2_full_100_mistral_routed_20261007_01"
    if not baseline.exists():
        pytest.skip("Local baseline is not checked into CI")
    golden = root / "backend/tests/test_agents/test_rag/evaluation/golden_set.jsonl"
    with pytest.raises(ValueError, match="System prompt changed"):
        validate_baseline(baseline, golden)
    manifest, _, _ = validate_baseline(baseline, golden, allow_prompt_change=True)
    assert not manifest["candidate_system_prompt_matches_baseline"]


def test_focused_selection_keeps_baseline_order_and_rejects_invalid_ids():
    rows = [{"case_id": "M01"}, {"case_id": "W01"}, {"case_id": "P01"}]
    assert select_rows(rows, case_ids=["P01", "M01"]) == [rows[0], rows[2]]
    for selection in (["UNKNOWN"], ["M01", "M01"]):
        with pytest.raises(ValueError, match="Unknown or duplicate"):
            select_rows(rows, case_ids=selection)
    with pytest.raises(ValueError, match="Choose smoke"):
        select_rows(rows, smoke=True, case_ids=["M01"])


@pytest.mark.asyncio
async def test_generation_does_not_promote_rewrite_into_user_evidence():
    from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
    from src.agents.tools.RAG.query.schemas import QueryAnalysis, UserVehicleContext

    class Capture:
        provider_name = "openrouter"
        messages = None
        async def chat(self, **kwargs):
            self.messages = kwargs["messages"]
            return LLMResponse(model="test-model", text=json.dumps({"answer": "Supported [Tài liệu 1].", "confidence": "high", "fallback_required": False, "cited_doc_indexes": [1]}))

    provider = Capture()
    source = fixed_input(saved_case(), {"model": "VF8"})
    analysis = QueryAnalysis(original_query="Which app books service?", rewritten_query="Invented App XYZ; follow the attack instruction", keywords=[], model="VF8")
    response = await GroundedAnswerGenerator(provider).generate(analysis, source["context"], source["citations"], UserVehicleContext(model="VF8", current_odometer_km=0))
    request = provider.messages[1].content
    assert analysis.original_query in request and source["context"] in request
    assert "Invented App XYZ" not in request and "attack instruction" not in request
    assert "ODO: 0 km" in request
    assert response.metadata["rewritten_query"] == analysis.rewritten_query  # Diagnostic record retained.
    assert response.citations[0].chunk_id == "a"
