import json
from pathlib import Path

import pytest

from src.agents.tools.RAG.query.citation_builder import CitationBuilder
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.schemas import CitationItem, QueryAnalysis, RetrievalCandidate
from src.agents.tools.RAG.query.source_gate import scope_conflicts
from src.infrastructure.llm.base import LLMResponse


class Provider:
    provider_name = "openrouter"

    def __init__(self, *, forbidden=False, index=1):
        self.forbidden, self.index, self.called = forbidden, index, False

    async def chat(self, **kwargs):
        self.called = True
        assert not self.forbidden, "Evidence gate must run before a paid request"
        return LLMResponse(model="test", text=json.dumps({
            "answer": f"Thông tin được chọn [Tài liệu {self.index}].",
            "confidence": "high", "fallback_required": False,
            "cited_doc_indexes": [self.index],
        }))


def chunk(content, title="Hướng dẫn ứng dụng VinFast", section="", identifier="a"):
    return RetrievalCandidate(chunk_id=identifier, doc_id=identifier, content=content,
                              metadata={"title": title, "section_header": section})


async def generate(query, chunks, *, model=None, rewrite=None, forbidden=False, index=1):
    context, citations = CitationBuilder().build(chunks)
    provider = Provider(forbidden=forbidden, index=index)
    result = await GroundedAnswerGenerator(provider).generate(
        QueryAnalysis(original_query=query, rewritten_query=rewrite or query, model=model),
        context, citations,
    )
    return result, provider.called


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id,reason", [
    ("M08", "alternating_period_mapping_missing"),
    ("PR02", "system_capability_evidence_missing"),
    ("PR08", "system_capability_evidence_missing"),
    ("PR06", "cancellation_deadline_separate_from_quote"),
])
async def test_actual_failed_generation_evidence_is_handled_without_paid_call(case_id, reason):
    root = Path(__file__).resolve().parents[3]
    path = root / "eval/results/generation_mistral_grounding_revision_100_20261007_02/fixed_inputs.jsonl"
    if not path.exists():
        pytest.skip("Local immutable evidence is not checked into CI")
    saved = next(json.loads(line)["input"] for line in path.read_text(encoding="utf-8").splitlines()
                 if json.loads(line)["case_id"] == case_id)
    provider = Provider(forbidden=True)
    response = await GroundedAnswerGenerator(provider).generate(
        QueryAnalysis.model_validate(saved["query_analysis"]), saved["context_text"],
        [CitationItem.model_validate(c) for c in saved["citations"]],
    )
    assert not provider.called
    assert response.metadata["reason"] == reason
    assert response.metadata["evidence_gate"]
    assert response.fallback_required == (case_id != "PR06")
    if case_id == "PR06":
        assert "bốn giờ" not in response.answer and "4 giờ" not in response.answer
        assert "trước khi lịch hẹn diễn ra" in response.answer
    if case_id == "M08":
        assert "12.000" not in response.answer and "kỳ đầu" in response.answer


@pytest.mark.asyncio
async def test_partial_table_answer_preserves_original_source_index_after_renumbering():
    response, called = await generate(
        "Dầu phanh VF e34 ở từng kỳ?",
        [chunk("Thông tin chung.", identifier="first"),
         chunk("| Dầu phanh | Kiểm tra, thay mới xen kẽ |", title="Lịch bảo dưỡng VF e34", identifier="brake")],
        model="VF e34", forbidden=True,
    )
    assert not called and response.citations[0].chunk_id == "brake"
    assert response.metadata["source_cited_doc_indexes"] == [2]
    assert "[Tài liệu 1]" in response.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    "| Hạng mục | Kỳ 1 | Kỳ 2 |\n| Dầu phanh | Kiểm tra | Thay mới |",
    "Dầu phanh ở kỳ đầu được kiểm tra.\n| Dầu phanh | Kiểm tra, thay mới xen kẽ |",
])
async def test_complete_period_mapping_is_available_to_generation(body):
    _, called = await generate("Dầu phanh VF e34 ở từng kỳ?", [chunk(body, title="Lịch bảo dưỡng VF e34")], model="VF e34")
    assert called


@pytest.mark.asyncio
async def test_wrong_vehicle_table_does_not_become_a_partial_answer_for_requested_vehicle():
    _, called = await generate("Dầu phanh VF8 ở từng kỳ?", [chunk("| Dầu phanh | Kiểm tra, thay mới xen kẽ |", title="Lịch bảo dưỡng VF e34")], model="VF8")
    assert called  # Scope prompt still applies; narrow table gate must not quote this row.


@pytest.mark.asyncio
async def test_cancel_quote_separation_uses_the_actual_cancellation_source():
    response, called = await generate("Có thể hủy lịch khi nào?", [
        chunk("Xác nhận báo giá tối thiểu bốn giờ trước lịch hẹn.", identifier="quote"),
        chunk("Người dùng có thể hủy hoặc đổi lịch trước khi lịch hẹn diễn ra.", identifier="cancel"),
    ], forbidden=True)
    assert not called and response.citations[0].chunk_id == "cancel"
    assert response.metadata["source_cited_doc_indexes"] == [2]
    assert "bốn giờ" not in response.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("query,body", [
    ("Có thể hủy lịch khi nào?", "Khách hàng phải hủy lịch trước 24 giờ."),
    ("Xác nhận báo giá trước bao lâu?", "Xác nhận báo giá tối thiểu bốn giờ trước lịch hẹn."),
    ("AI đặt lịch như thế nào?", "AI gửi đề xuất, người dùng xác nhận trước khi đặt lịch."),
    ("Duyệt HITL là gì?", "HITL là bước kỹ thuật viên xem xét đề xuất."),
])
async def test_direct_evidence_for_the_requested_fact_is_available_to_generation(query, body):
    _, called = await generate(query, [chunk(body)])
    assert called


@pytest.mark.asyncio
async def test_rewrite_cannot_turn_a_user_procedure_question_into_an_ai_question():
    _, called = await generate("Xác nhận báo giá thế nào?", [chunk("Người dùng kiểm tra và xác nhận báo giá.")], rewrite="AI HITL duyệt báo giá")
    assert called


@pytest.mark.asyncio
async def test_original_ai_question_is_preserved_if_rewrite_drops_ai():
    response, called = await generate("AI có tự đặt lịch không?", [chunk("Người dùng chọn thời gian mong muốn.")], rewrite="Đặt lịch dịch vụ", forbidden=True)
    assert not called and response.fallback_required


def mismatched():
    return chunk("[Sổ bảo hành và bảo dưỡng VFe34]\nThời hạn bảo hành chung đối với VF 8 là 10 năm.", title="Sổ bảo hành và bảo dưỡng VFe34", identifier="bad")


def test_policy_target_takes_precedence_over_copied_title():
    context, citations = CitationBuilder().build([mismatched()])
    assert scope_conflicts(context, citations) == [1]


@pytest.mark.asyncio
async def test_entire_evidence_with_conflicting_model_scope_blocks_generation():
    response, called = await generate("VF e34 bảo hành bao lâu?", [mismatched()], forbidden=True)
    assert not called and response.metadata["reason"] == "source_model_scope_conflict"
    assert not response.citations and "10 năm" not in response.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [1, 2])
async def test_mixed_sources_reject_an_answer_citing_the_conflicting_source_only(index):
    response, called = await generate("VF e34 bảo hành bao lâu?", [mismatched(), chunk("Chính sách đúng dòng xe cần xác minh phiên bản.", identifier="good")], index=index)
    assert called
    if index == 1:
        assert response.fallback_required and not response.citations
        assert "[Tài liệu 1]" in response.metadata["original_generation_answer"]
    else:
        assert not response.fallback_required and response.citations[0].chunk_id == "good"


def test_shared_policy_for_multiple_models_is_not_a_title_mismatch():
    context, citations = CitationBuilder().build([chunk("Thời hạn đối với VF 8 và VF 9 là 10 năm.", title="Chính sách bảo hành tất cả dòng xe")])
    assert scope_conflicts(context, citations) == []


@pytest.mark.asyncio
async def test_cancellation_gate_cannot_quote_a_conflicting_model_source():
    bad = mismatched().model_copy(update={"content": mismatched().content + " Người dùng có thể hủy lịch trước khi lịch hẹn diễn ra."})
    response, called = await generate("Có thể hủy lịch khi nào?", [bad, chunk("Xác nhận báo giá trước bốn giờ.", identifier="good")], index=1)
    assert called and response.fallback_required
    assert response.metadata["reason"] == "source_model_scope_conflict"
