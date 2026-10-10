import json

import pytest

from src.agents.tools.RAG.query.citation_builder import CitationBuilder
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.schemas import QueryAnalysis, RetrievalCandidate
from src.infrastructure.llm.base import LLMResponse


class CaptureProvider:
    provider_name = "openrouter"

    def __init__(self, forbidden=False):
        self.called = False
        self.forbidden = forbidden

    async def chat(self, **kwargs):
        self.called = True
        assert not self.forbidden, "Missing procedure must be handled before generation"
        return LLMResponse(model="test", text=json.dumps({"answer": "Information [Tài liệu 1].", "confidence": "high", "fallback_required": False, "cited_doc_indexes": [1]}))


async def answer(query, chunks, *, forbidden):
    context, citations = CitationBuilder().build(chunks)
    provider = CaptureProvider(forbidden)
    response = await GroundedAnswerGenerator(provider).generate(QueryAnalysis(original_query=query, rewritten_query=query), context, citations)
    return response, provider.called


def chunk(content, section, identifier="a"):
    return RetrievalCandidate(chunk_id=identifier, doc_id="manual", content=content, metadata={"title": "Hướng dẫn ứng dụng VinFast", "section_header": section})


@pytest.mark.asyncio
async def test_tracking_appointment_does_not_establish_app_creation_steps():
    result, called = await answer("Đặt lịch qua app như thế nào?", [chunk("Vào Dịch vụ, chọn lịch hẹn sắp tới để theo dõi. Xác nhận báo giá tối thiểu 4 giờ trước lịch hẹn.", "Theo dõi quá trình sửa chữa")], forbidden=True)
    assert not called and result.fallback_required and result.confidence == "low"
    assert result.metadata["reason"] == "app_booking_steps_missing"
    assert "không hỗ trợ đặt lịch" not in result.answer


@pytest.mark.asyncio
async def test_actual_new_appointment_steps_are_available_to_generation():
    result, called = await answer("Hướng dẫn đặt lịch qua ứng dụng", [chunk("Bước 1: Chọn loại dịch vụ. Bước 2: Chọn thời gian mong muốn, kiểm tra và xác nhận đặt lịch.", "Đặt lịch sửa chữa hoặc bảo dưỡng")], forbidden=False)
    assert called and not result.fallback_required


@pytest.mark.asyncio
async def test_rain_warning_does_not_establish_immediate_disconnection_sop():
    result, called = await answer("Xe đang sạc thì bị mưa có sao không?", [chunk("Sạc tối đa 24 kW.", "Thông số", "other"), chunk("Khách hàng không nên sạc pin khi trời mưa to hoặc có sấm sét.", "Lưu ý an toàn", "weather")], forbidden=True)
    assert not called and result.fallback_required
    assert result.citations[0].chunk_id == "weather"
    assert result.metadata["source_cited_doc_indexes"] == [2]
    assert "[Tài liệu 1]" in result.answer
    assert "ngay lập tức" not in result.answer


@pytest.mark.asyncio
async def test_an_explicit_rain_charging_procedure_is_not_blocked():
    _, called = await answer("Xe đang sạc gặp mưa", [chunk("Bước 1: Liên hệ kỹ thuật để được hướng dẫn theo tình huống mưa.", "Quy trình xử lý khi xe đang sạc gặp mưa")], forbidden=False)
    assert called


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["Mua bộ sạc giá bao nhiêu?", "mua bo sac gia bao nhieu", "Giá thiết bị sạc tại nhà?"])
async def test_buying_a_charger_is_not_mistaken_for_rain(query):
    _, called = await answer(query, [chunk("Giá bộ sạc là 10.000.000 đồng.", "Giá thiết bị")], forbidden=False)
    assert called
