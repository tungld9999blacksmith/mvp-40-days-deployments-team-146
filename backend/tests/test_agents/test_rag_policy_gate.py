import json
from pathlib import Path

import pytest

from src.agents.tools.RAG.query.citation_builder import CitationBuilder
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.schemas import CitationItem, QueryAnalysis, RetrievalCandidate
from src.infrastructure.llm.base import LLMResponse


class Provider:
    provider_name = "openrouter"

    def __init__(self, answer="Nội dung [Tài liệu 1].", indexes=None, forbidden=False):
        self.answer, self.indexes, self.forbidden, self.called = answer, indexes or [1], forbidden, False

    async def chat(self, **kwargs):
        self.called = True
        assert not self.forbidden, "Source-proven expiry must not need a paid call"
        return LLMResponse(model="test", text=json.dumps({"answer": self.answer, "confidence": "high", "fallback_required": False, "cited_doc_indexes": self.indexes}))


def chunk(body, title="Quy trình dịch vụ", identifier="a"):
    return RetrievalCandidate(chunk_id=identifier, doc_id=identifier, content=body, metadata={"title": title})


async def generate(query, chunks, provider, model=None):
    context, citations = CitationBuilder().build(chunks)
    response = await GroundedAnswerGenerator(provider).generate(QueryAnalysis(original_query=query, rewritten_query=query, model=model), context, citations)
    return response


def vehicle_rule(years=7, model="VF 3", km="160.000"):
    return f"Thời hạn bảo hành chung đối với {model} là {years} năm kể từ Ngày Kích Hoạt Bảo Hành hoặc {km} km tùy thuộc vào điều kiện nào đến trước."


def feedback_rule(days, suffix=""):
    return f"Khách hàng làm dịch vụ sẽ được gọi điện để ghi nhận phản hồi trong vòng {days} ngày sau khi bảo dưỡng xe{suffix}."


def frozen(identifier):
    root = Path(__file__).resolve().parents[3]
    directory = root / "eval/results/generation_mistral_source_gate_100_20261008_08"
    if not directory.exists():
        pytest.skip("Local immutable results are not checked into CI")
    saved = next(json.loads(s)["input"] for s in (directory / "fixed_inputs.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(s)["case_id"] == identifier)
    old = next(json.loads(s) for s in (directory / "case_results.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(s)["case_id"] == identifier)
    return saved, old


@pytest.mark.asyncio
async def test_actual_pr03_claim_is_replaced_by_two_source_quotes_without_losing_workflow():
    saved, old = frozen("PR03")
    indexes = old["response"]["metadata"]["source_cited_doc_indexes"]
    # Stored delivered indexes are renumbered; reconstruct provider-context refs.
    import re
    raw_answer = re.sub(r"\[Tài liệu (\d+)\]", lambda m: f"[Tài liệu {indexes[int(m[1])-1]}]", old["answer"])
    provider = Provider(raw_answer, indexes)
    result = await GroundedAnswerGenerator(provider).generate(QueryAnalysis.model_validate(saved["query_analysis"]), saved["context_text"], [CitationItem.model_validate(c) for c in saved["citations"]])
    assert provider.called and result.fallback_required and result.confidence == "low"
    assert "2–3 ngày" not in result.answer
    assert "2 ngày sau khi bảo dưỡng" in result.answer and "3 ngày sau khi xe ra xưởng" in result.answer
    assert all(step in result.answer for step in ("Bước 1", "Bước 2", "Bước 3", "Bước 4", "Bước 5"))
    assert "24 giờ" in result.answer
    assert result.metadata["original_generation_answer"] == raw_answer
    assert result.metadata["source_followup_rules"][1]["original_index"] == 4
    assert result.metadata["source_cited_doc_indexes"] == indexes
    assert 4 in indexes and result.citations[-1].document_id == "pricing_bao_gia_dich_vu_ALL"


@pytest.mark.asyncio
async def test_actual_w20_adds_conditional_expiry_and_preserves_vehicle_commercial_scope():
    saved, _ = frozen("W20")
    provider = Provider(forbidden=True)
    result = await GroundedAnswerGenerator(provider).generate(QueryAnalysis.model_validate(saved["query_analysis"]), saved["context_text"], [CitationItem.model_validate(c) for c in saved["citations"]])
    assert not provider.called and "Nếu đã đủ 7 năm kể từ ngày kích hoạt" in result.answer
    assert "dù chưa đạt 160.000 km" in result.answer
    assert "thương mại" in result.answer and "3 năm hoặc 100.000 km" in result.answer
    assert "8 năm" not in result.answer and "10 năm" not in result.answer
    assert result.metadata["vehicle_eligibility_verified"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("duration", ["2–3", "2-3", "hai đến ba", "3", "**2–3**", "__2-3__", "`hai đến ba`"])
async def test_disputed_duration_is_not_merged_or_selected_from_one_source(duration):
    answer = f"Tiếp nhận xe [Tài liệu 1].\nKhách hàng được gọi điện ghi nhận phản hồi trong vòng {duration} ngày [Tài liệu 1].\nPhản ánh được phản hồi trong 24 giờ [Tài liệu 2]."
    response = await generate("Quy trình bảo dưỡng thế nào?", [chunk(feedback_rule(2)), chunk(feedback_rule(3), identifier="b")], Provider(answer, [1, 2]))
    assert "Tiếp nhận xe" in response.answer and "24 giờ" in response.answer
    assert "trong vòng 2 ngày" in response.answer and "trong vòng 3 ngày" in response.answer
    assert response.metadata["removed_followup_claims"]
    assert response.metadata["source_cited_doc_indexes"] == [1, 2]


@pytest.mark.asyncio
async def test_markdown_inside_call_and_feedback_words_cannot_hide_a_disputed_claim():
    original = "Khách hàng được *gọi* **điện** ghi nhận **phản hồi** trong vòng **2–3** ngày [Tài liệu 1]."
    result = await generate("Quy trình bảo dưỡng thế nào?", [chunk(feedback_rule(2)), chunk(feedback_rule(3), identifier="b")], Provider(original))
    assert result.metadata["original_generation_answer"] == original
    assert result.metadata["removed_followup_claims"]
    assert "**2–3**" not in result.answer


@pytest.mark.asyncio
async def test_conflicting_source_at_index_three_is_retained_and_renumbered_by_identity():
    response = await generate("Khi nào gọi điện chăm sóc sau bảo dưỡng?", [chunk(feedback_rule(2)), chunk("Thông tin khác.", identifier="other"), chunk(feedback_rule(3), identifier="third")], Provider(feedback_rule(2) + " [Tài liệu 1]."))
    assert response.metadata["source_cited_doc_indexes"] == [1, 3]
    assert response.citations[1].chunk_id == "third"
    assert "[Tài liệu 2]" in response.answer and "[Tài liệu 3]" not in response.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [
    [chunk(feedback_rule(2)), chunk(feedback_rule(2), identifier="b")],
    [chunk(feedback_rule(2)), chunk("Nhắc khách hàng trước 3 ngày để đặt lịch.", identifier="b")],
    [chunk(feedback_rule(2)), chunk("Đối với xe thương mại, khách hàng được gọi điện ghi nhận phản hồi trong vòng 3 ngày sau khi bảo dưỡng xe.", identifier="b")],
])
async def test_agreement_pre_service_reminders_and_explicitly_different_scopes_do_not_create_conflict(chunks):
    provider = Provider("Thông tin quy trình [Tài liệu 1].")
    result = await generate("Quy trình bảo dưỡng thế nào?", chunks, provider)
    assert provider.called and not result.fallback_required
    assert "source_followup_rules" not in result.metadata


@pytest.mark.asyncio
async def test_unrelated_answer_does_not_acquire_post_service_policy_from_retrieval_noise():
    response = await generate("Giá bảo dưỡng bao nhiêu?", [chunk(feedback_rule(2)), chunk(feedback_rule(3), identifier="b")], Provider("Giá được cung cấp [Tài liệu 1]."))
    assert not response.fallback_required and "gọi điện" not in response.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "Xe VF3 dùng 6 năm còn bảo hành không?", "Pin VF3 dùng 7 năm còn bảo hành không?",
    "Xe VF8 dùng 7 năm còn bảo hành không?", "Xe VF3 chưa đủ 7 năm còn bảo hành không?",
    "Xe VF3 dùng 6 hoặc 7 năm còn bảo hành không?", "Bảo hành VF3 bao nhiêu năm?",
])
async def test_unknown_eligibility_component_other_model_or_unreached_limit_is_not_declared_expired(query):
    provider = Provider()
    await generate(query, [chunk(vehicle_rule(), title="Sổ bảo hành VF3")], provider)
    assert provider.called


@pytest.mark.asyncio
async def test_expiry_uses_matching_source_and_keeps_original_source_identity():
    result = await generate("Xe VF3 dùng 7 năm còn bảo hành không?", [chunk("Thông tin chung."), chunk(vehicle_rule(), title="Sổ bảo hành VF3", identifier="vehicle")], Provider(forbidden=True))
    assert result.citations[0].chunk_id == "vehicle" and result.metadata["source_cited_doc_indexes"] == [2]
    assert "[Tài liệu 1]" in result.answer


@pytest.mark.asyncio
async def test_generic_rule_is_not_hardcoded_to_vf3_or_seven_years():
    result = await generate("Xe VF5 dùng 9 năm còn bảo hành không?", [chunk(vehicle_rule(8, "VF 5", "180.000"), title="Sổ bảo hành VF5")], Provider(forbidden=True))
    assert "Nếu đã đủ 8 năm" in result.answer and "180.000 km" in result.answer
    assert "7 năm" not in result.answer


@pytest.mark.asyncio
async def test_different_direct_vehicle_limits_cannot_be_resolved_by_selecting_the_first():
    provider = Provider()
    await generate("Xe VF3 dùng 7 năm còn bảo hành không?", [chunk(vehicle_rule()), chunk(vehicle_rule(10), identifier="b")], provider)
    assert provider.called


@pytest.mark.asyncio
async def test_incomplete_limit_without_activation_basis_does_not_certify_vehicle_expiry():
    provider = Provider()
    await generate("Xe VF3 dùng 7 năm còn bảo hành không?", [chunk("Bảo hành xe VF3 7 năm hoặc 160.000 km.")], provider)
    assert provider.called
