import pytest
from offline_evaluator66 import citation_obligations, diagnose, evidence_axes


@pytest.mark.parametrize("fallback", [True, False])
def test_fallback_is_answerability_not_source_verification(fallback):
    producer = {"live": {"rag": [{"response": {"fallback_required": fallback, "metadata": {}}}]}}
    result = evidence_axes(producer)
    assert result["rag_observations"][0]["source_authority"] == "NOT_ASSESSED"
    assert result["source_authority_rollup"] == "NOT_INDEPENDENTLY_VERIFIED"
    assert result["content_correctness"] == "NOT_EVALUATED"


def test_explicit_source_uncertainty_remains_even_without_fallback():
    result = evidence_axes({"live": {"rag": [{"response": {"fallback_required": False, "metadata": {"source_rule_verified": False}}}]}})
    assert result["source_authority_rollup"] == "EXPLICITLY_UNVERIFIED"


def test_rule_verified_is_never_independent_source_truth():
    result = evidence_axes({"live": {"rag": [{"response": {"metadata": {"source_rule_verified": True}}}]}})
    assert result["rag_observations"][0]["source_authority"] == "RULE_CHECK_ONLY"
    assert not result["rag_observations"][0]["independent_source_verified"]


def test_no_rag_authority_not_applicable_does_not_certify_content():
    result = evidence_axes({})
    assert result["source_authority_rollup"] == "NOT_APPLICABLE"
    assert result["content_correctness"] == "NOT_EVALUATED"


def test_scoped_abstention_does_not_get_automatic_fail_or_pass():
    result = citation_obligations({"answer": "Các đoạn tài liệu được cung cấp chưa xác định nội dung này.", "citations": [], "has_rag": True})
    assert not result["missing_citation_requires_review"]
    assert result["abstention_truth_and_completeness"] == "NOT_EVALUATED"


@pytest.mark.parametrize("answer", ["Pin bảo hành 8 năm.", "Tất cả tài liệu đều không có hướng dẫn này."])
def test_factual_or_broad_negative_claims_still_require_review(answer):
    assert citation_obligations({"answer": answer, "has_rag": True})["missing_citation_requires_review"]


def test_inline_citation_index_is_not_claim_entailment():
    result = citation_obligations({"answer": "Warranty [Tài liệu 2]", "has_rag": True, "citations": [{"index": 1}]})
    assert result["missing_inline_indexes"] == [2] and result["claim_support"] == "NOT_EVALUATED"


def test_old_fail_labels_are_never_replaced_by_new_diagnostics():
    sample = {"sample_id": "old", "answer": "Các đoạn tài liệu được cung cấp chưa xác định nội dung này.", "tool_calls": [], "has_rag": True}
    result = diagnose(sample, {}, "FAIL")
    assert result["original_status_retained"] == "FAIL" and result["replacement_status"] is None


@pytest.mark.parametrize("record_index", [0, 1])
def test_replay_uses_expanded_evidence_and_final_query_analysis(record_index):
    import json

    from offline_revision66 import PRIOR, ROOT, recorded_inputs

    indexes = json.loads((PRIOR / "judge_private_index.json").read_text(encoding="utf-8"))
    origin = [item for item in indexes if item["case_id"] == "NEW-R04"][record_index]
    rows = [json.loads(line) for line in (ROOT / origin["producer"] / "case_results.jsonl").read_text(encoding="utf-8").splitlines()]
    row = next(item for item in rows if item["case_id"] == "NEW-R04")
    analysis, context, citations, vehicle = recorded_inputs(row["live"]["rag"][0])
    assert analysis.category == "maintenance"
    assert "12.000km" in context and "120" in context
    assert "expanded_chunk_ids" in row["live"]["rag"][0]["response"]["metadata"]["evidence_chunks"][0]["metadata"]
    assert len(citations) == 3 and vehicle.model == "VFE34"


@pytest.mark.parametrize("mutation", [None, "count", "duplicate", "unavailable", "date", "workshop"])
def test_slot_controls_reject_incorrect_business_claims(mutation):
    from agent_judge_audit65 import slot_claim_check

    answer = "Xưởng workshop-01, ngày 09/10/2026 có 1 khung giờ khả dụng:\n- 10:00: còn 4 chỗ"
    tool = {"workshop_id": "workshop-01", "date": "2026-10-09", "slots": [
        {"time_slot": "10:00", "remaining": 4, "available": True},
        {"time_slot": "11:00", "remaining": 0, "available": False},
    ]}
    if mutation == "count":
        answer = answer.replace("có 1", "có 2")
    elif mutation == "duplicate":
        answer = answer.replace("có 1", "có 2") + "\n- 10:00: còn 4 chỗ"
    elif mutation == "unavailable":
        answer = answer.replace("10:00: còn 4", "11:00: còn 0")
    elif mutation == "date":
        answer = answer.replace("09/10/2026", "10/10/2026")
    elif mutation == "workshop":
        answer = answer.replace("workshop-01", "workshop-02")
    result = slot_claim_check({"answer": answer, "tool_calls": [{"name": "get_available_slots", "result": tool}]})
    assert result["applicable"] and result["claim_matches"] is (mutation is None)
