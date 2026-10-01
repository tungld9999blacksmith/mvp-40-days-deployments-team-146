from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_rag_pipeline: Any | None = None


def _get_rag_pipeline() -> Any:
    """Khởi tạo lazy singleton RAGPipeline kết nối Qdrant Cloud + BM25 + FlashRank + Gemini."""
    global _rag_pipeline
    if _rag_pipeline is None:
        from src.agents.tools.RAG.ingestion.qdrant_store import QdrantVectorStore
        from src.agents.tools.RAG.query.hybrid import HybridRetriever
        from src.agents.tools.RAG.query.rag_pipeline import RAGPipeline
        from src.agents.tools.RAG.query.reranker import RerankerService
        from src.agents.tools.RAG.query.rewriter import QueryRewriter
        from src.infrastructure.llm.dependency import get_llm_provider

        try:
            vs = QdrantVectorStore()
            hybrid = HybridRetriever(vector_store=vs)
            hybrid.sync_bm25_from_vector_store()
            llm = get_llm_provider()

            _rag_pipeline = RAGPipeline(
                rewriter=QueryRewriter(llm_provider=llm),
                hybrid_retriever=hybrid,
                reranker=RerankerService(provider="auto"),
            )
            logger.info("Đã khởi tạo thành công RAGPipeline (Qdrant Cloud) cho LangGraph Tool.")
        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo RAGPipeline: {e}")
            raise e

    return _rag_pipeline


def _format_rag_response(response: Any) -> str:
    """Format kết quả từ RAGResponse thành văn bản chi tiết kèm nguồn trích dẫn cho Agent."""
    output = response.answer
    if response.citations:
        output += "\n\n[Tài liệu tham chiếu chính hãng]:"
        for idx, c in enumerate(response.citations, 1):
            sec_info = f" - Mục: {c.section}" if c.section else ""
            output += f"\n  [{idx}] {c.title}{sec_info}"
    return output


@tool
def search_ev_knowledge(
    query: str,
    model: str = "",
    category: str = "",
) -> str:
    """Tìm kiếm thông tin kỹ thuật, bảo dưỡng, bảo hành, bảng giá trong Cẩm nang xe điện VinFast trên Qdrant Cloud.

    Args:
        query: Câu hỏi hoặc từ khóa cần tra cứu (ví dụ: 'chính sách bảo hành pin', 'chi phí bảo dưỡng mốc 24.000 km')
        model: Dòng xe cần tra cứu (tùy chọn: 'VF3', 'VF5', 'VF6', 'VF7', 'VF8', 'VF9', 'VFe34', 'ALL')
        category: Phân loại thông tin (tùy chọn: 'maintenance', 'warranty', 'pricing', 'battery', 'procedure')

    Returns:
        Câu trả lời chính xác có nguồn dẫn chính hãng
    """
    pipeline = _get_rag_pipeline()
    from src.agents.tools.RAG.query.schemas import UserVehicleContext

    clean_model = model.strip().upper() if model else None
    vehicle_context = UserVehicleContext(model=clean_model) if clean_model else None

    response = pipeline.query_sync(
        query=query,
        vehicle_context=vehicle_context,
        top_k=3,
    )
    return _format_rag_response(response)


@tool
def get_maintenance_schedule_rag(model: str, km: int) -> str:
    """Tra cứu các hạng mục bảo dưỡng định kỳ theo dòng xe và số km từ cẩm nang chính hãng.

    Args:
        model: Tên dòng xe điện (ví dụ: 'VF5', 'VF6', 'VF8', 'VFe34')
        km: Số km hiện tại hoặc mốc km cần bảo dưỡng (ví dụ: 12000, 24000, 48000)

    Returns:
        Danh sách hạng mục bảo dưỡng chi tiết và lưu ý kỹ thuật
    """
    clean_model = model.strip().upper()
    query = f"Hạng mục bảo dưỡng định kỳ mốc {km} km xe {clean_model}"
    pipeline = _get_rag_pipeline()
    from src.agents.tools.RAG.query.schemas import UserVehicleContext

    vehicle_context = UserVehicleContext(model=clean_model, current_odometer_km=km)
    response = pipeline.query_sync(
        query=query,
        vehicle_context=vehicle_context,
        top_k=3,
    )
    return _format_rag_response(response)


@tool
def get_warranty_policy_rag(model: str, component: str = "") -> str:
    """Tra cứu chính sách, điều kiện và các trường hợp loại trừ bảo hành chính hãng từ VinFast.

    Args:
        model: Tên dòng xe điện (ví dụ: 'VF8', 'VF9', 'VF5', 'VFe34')
        component: Bộ phận cần tra cứu (ví dụ: 'pin', 'động cơ', 'khung gầm', 'ắc quy 12V', 'màn hình')

    Returns:
        Chính sách bảo hành, thời hạn năm, số km tối đa và điều kiện áp dụng
    """
    clean_model = model.strip().upper()
    comp_text = f" {component}" if component else ""
    query = f"Chính sách điều kiện bảo hành{comp_text} cho xe {clean_model}"
    pipeline = _get_rag_pipeline()
    from src.agents.tools.RAG.query.schemas import UserVehicleContext

    vehicle_context = UserVehicleContext(model=clean_model)
    response = pipeline.query_sync(
        query=query,
        vehicle_context=vehicle_context,
        top_k=3,
    )
    return _format_rag_response(response)

