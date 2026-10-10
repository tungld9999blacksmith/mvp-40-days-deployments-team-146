"""Regression for source-literal numbers and incomplete period table actions."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.maintenance_gate import maintenance_evidence_gate, ragged_period_table
from src.agents.tools.RAG.query.schemas import CitationItem, QueryAnalysis

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / "eval/results/generation_mistral_policy_final_100_20261008_10/fixed_inputs.jsonl"
BODY = """| Km hoặc Tháng tương ứng | 12.000 | 24.000 | 36.000 |
| Dầu phanh | Kiểm tra, thay mới xen kẽ |
| Nước làm mát pin/động cơ điện | Thay mới ở tháng thứ 120 hoặc sau 12.000km. Thời gian còn lại kiểm tra thường xuyên |
| Pin |
| Dây cáp của hệ thống điện áp cao |
| Cổng sạc |"""
QUERIES = [
    "Nước làm mát pin và động cơ điện VF e34 cần thay hay kiểm tra định kỳ?",
    "Trong bảo dưỡng VF e34, những hạng mục nào liên quan đến pin cao áp và cổng sạc?",
    "Xe VF e34 đến 40.000 km cần thay những phụ tùng gì?",
]


def evidence(body=BODY, query=QUERIES[0], index=1, section="Lịch bảo dưỡng xe VF e34"):
    citations = [CitationItem(document_id=f"doc-{i}", chunk_id=f"chunk-{i}", title="Lịch bảo dưỡng", section=section) for i in range(index)]
    context = f'[Tài liệu {index}] (ID: doc-{index-1})\n- Nội dung trích xuất:\n"""\n{body}\n"""'
    analysis = QueryAnalysis(original_query=query, rewritten_query=query, model="VFe34")
    return analysis, context, citations


@pytest.mark.parametrize(("query", "reason"), list(zip(QUERIES, ["coolant_source_value_unverified", "maintenance_component_actions_missing", "maintenance_period_mapping_missing"], strict=True)))
def test_observed_synthetic_failure(query, reason):
    result = maintenance_evidence_gate(*evidence(query=query))
    assert result and result.metadata["reason"] == reason
    assert result.fallback_required and result.confidence == "low"
    assert result.metadata["source_rule_verified"] is False
    assert "120.000" not in result.answer


def test_coolant_quote_is_literal_not_a_corrected_rule():
    result = maintenance_evidence_gate(*evidence())
    assert result.metadata["literal_source_row"] in result.answer
    assert "12.000km" in result.answer
    assert "120.000" not in result.answer
    assert "không tự sửa" in result.answer


def test_missing_component_actions_are_not_filled():
    result = maintenance_evidence_gate(*evidence(query=QUERIES[1]))
    assert result.metadata["literal_component_labels"] == ["Pin", "Dây cáp của hệ thống điện áp cao", "Cổng sạc"]
    assert "chưa thể kết luận" in result.answer


def test_preserve_original_source_identity_after_selection():
    result = maintenance_evidence_gate(*evidence(index=3))
    assert result.metadata["source_cited_doc_indexes"] == [3]
    assert result.citations[0].chunk_id == "chunk-2"
    assert "[Tài liệu 1]" in result.answer


@pytest.mark.parametrize("query", ["Nước làm mát VF8 cần thay định kỳ thế nào?", "Pin chìa khóa VF e34 cần thay định kỳ khi nào?", "Giá nước làm mát VF e34 bao nhiêu?", "Xe VF e34 hoặc VF8 cần thay phụ tùng tại40.000km nào?", "Xe cần thay phụ tùng ở40.000km nào?"])
def test_unrelated_or_different_model_not_intercepted(query):
    assert maintenance_evidence_gate(*evidence(query=query)) is None


def test_rewrite_model_does_not_override_original_model():
    analysis, context, citations = evidence(query=QUERIES[0].replace("VF e34", "VF8"))
    analysis.rewritten_query = QUERIES[0]
    assert maintenance_evidence_gate(analysis, context, citations) is None


def test_complete_table_retains_empty_action_cells():
    body = "| Km hoặc Tháng tương ứng | 12.000 | 24.000 | 40.000 |\n| Pin | KT | | KT |\n| Cổng sạc | KT | | KT |"
    assert not ragged_period_table(body)
    assert maintenance_evidence_gate(*evidence(body=body, query=QUERIES[2])) is None


def test_correct_literal_120000_is_not_marked_suspicious():
    assert maintenance_evidence_gate(*evidence(body=BODY.replace("12.000km", "120.000km"))) is None


def test_direct_same_model_milestone_rule_reaches_generation():
    body = BODY + "\nTại 40.000 km, thay lọc gió điều hòa theo lịch bảo dưỡng xe VF e34."
    assert maintenance_evidence_gate(*evidence(body=body, query=QUERIES[2])) is None


def test_warranty_mileage_is_not_a_maintenance_replacement_rule():
    body = BODY + "\nPhụ tùng thay thế có thời hạn bảo hành 2 năm hoặc 40.000 km kể từ ngày mua."
    result = maintenance_evidence_gate(*evidence(body=body, query=QUERIES[2]))
    assert result.metadata["reason"] == "maintenance_period_mapping_missing"


def test_explicit_component_actions_not_intercepted():
    body = BODY.replace("| Pin |", "| Pin | Kiểm tra |").replace("| Cổng sạc |", "| Cổng sạc | Kiểm tra |")
    assert maintenance_evidence_gate(*evidence(body=body, query=QUERIES[1])) is None


def test_missing_coolant_row_is_not_invented_in_component_answer():
    body = "\n".join(line for line in BODY.splitlines() if "Nước làm mát" not in line)
    result = maintenance_evidence_gate(*evidence(body=body, query=QUERIES[1]))
    assert result and "làm mát" not in result.answer


def test_different_model_direct_rule_does_not_fill_missing_requested_table():
    analysis, context, citations = evidence(query=QUERIES[2])
    _, other_context, other_citations = evidence(body="Tại 40.000 km, thay lọc gió điều hòa theo lịch bảo dưỡng VF8.", section="Lịch bảo dưỡng VF8", index=2)
    citations.append(other_citations[1])
    result = maintenance_evidence_gate(analysis, context + "\n" + other_context, citations)
    assert result and result.metadata["reason"] == "maintenance_period_mapping_missing"


@pytest.mark.parametrize("case_id", ["M07", "M18", "M23"])
@pytest.mark.asyncio
async def test_frozen_case_is_handled_before_provider(case_id):
    if not FROZEN.exists():
        pytest.skip("Local immutable run not distributed in CI; synthetic regressions cover the same failure")
    rows = [json.loads(line) for line in FROZEN.read_text(encoding="utf-8").splitlines()]
    frozen = next(r["input"] for r in rows if r["case_id"] == case_id)
    provider = AsyncMock()
    # Populate the citations from the saved context, preserving their original IDs.
    result = await GroundedAnswerGenerator(provider).generate(QueryAnalysis.model_validate(frozen["query_analysis"]), frozen["context_text"], [CitationItem.model_validate(c) for c in frozen["citations"]])
    assert result.fallback_required and result.metadata.get("evidence_gate")
    provider.chat.assert_not_awaited()
