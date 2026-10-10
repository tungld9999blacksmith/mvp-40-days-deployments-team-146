from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool, tool

from src.agents.evidence import rag_artifact

logger = logging.getLogger(__name__)

_rag_pipeline: Any | None = None
_rag_pipeline_lock = threading.Lock()


def _get_rag_pipeline() -> Any:
    """Khởi tạo lazy singleton RAGPipeline kết nối Qdrant Cloud + BM25 + FlashRank + Gemini."""
    global _rag_pipeline
    with _rag_pipeline_lock:  # warm-up and the first chat may race to build it
        if _rag_pipeline is None:
            _rag_pipeline = _build_rag_pipeline()
    return _rag_pipeline


def _build_rag_pipeline() -> Any:
    from ..ingestion.qdrant_store import QdrantVectorStore
    from .hybrid import HybridRetriever
    from .rag_pipeline import RAGPipeline
    from .reranker import RerankerService
    from .rewriter import QueryRewriter

    try:
        from src.infrastructure.llm.dependency import get_llm_provider_for_stage
    except ImportError:
        from infrastructure.llm.dependency import get_llm_provider_for_stage  # type: ignore

    try:
        vs = QdrantVectorStore()
        hybrid = HybridRetriever(vector_store=vs)
        hybrid.sync_bm25_from_vector_store()
        llm = get_llm_provider_for_stage("rewrite")

        pipeline = RAGPipeline(
            rewriter=QueryRewriter(llm_provider=llm),
            hybrid_retriever=hybrid,
            reranker=RerankerService(provider="auto"),
        )
        logger.info("Đã khởi tạo thành công RAGPipeline (Qdrant Cloud) cho LangGraph Tool.")
        return pipeline
    except Exception as e:
        logger.error(f"Lỗi khi khởi tạo RAGPipeline: {e}")
        raise e


def warm_up_rag_pipeline() -> None:
    """Build the pipeline (Qdrant client, BM25 index, reranker: ~4 s) before the first question."""
    try:
        _get_rag_pipeline()
    except Exception:  # noqa: BLE001 — the first question retries and reports it
        logger.warning("RAG pipeline warm-up failed", exc_info=True)


def _format_rag_response(response: Any) -> str:
    """Format kết quả từ RAGResponse thành văn bản chi tiết kèm nguồn trích dẫn cho Agent."""
    output = response.answer
    if response.citations:
        output += "\n\n[Tài liệu tham chiếu chính hãng]:"
        for idx, c in enumerate(response.citations, 1):
            sec_info = f" - Mục: {c.section}" if c.section else ""
            output += f"\n  [{idx}] {c.title}{sec_info}"
    return output


def _search_args(query: str, model: str, category: str) -> dict[str, Any]:
    from .schemas import UserVehicleContext

    clean_model = model.strip().upper() if model else None
    vehicle_context = UserVehicleContext(model=clean_model) if clean_model else None
    return {"query": query, "vehicle_context": vehicle_context, "category": category}


def _maintenance_args(model: str, km: int) -> dict[str, Any]:
    from .schemas import UserVehicleContext

    clean_model = model.strip().upper()
    return {
        "query": f"Hạng mục bảo dưỡng định kỳ mốc {km} km xe {clean_model}",
        "vehicle_context": UserVehicleContext(model=clean_model, current_odometer_km=km),
        "category": "maintenance",
    }


def _warranty_args(model: str, component: str) -> dict[str, Any]:
    from .schemas import UserVehicleContext

    clean_model = model.strip().upper()
    comp_text = f" {component}" if component else ""
    return {
        "query": f"Chính sách điều kiện bảo hành{comp_text} cho xe {clean_model}",
        "vehicle_context": UserVehicleContext(model=clean_model),
        "category": "warranty",
    }


def build_rag_tools(pipeline_provider: Callable[[], Any]) -> list[BaseTool]:
    """Bind a lazy RAG pipeline provider without changing tool inputs.

    The agent awaits the async variants: the query runs on the shared RAG loop and is
    cancelled with the turn. ``invoke`` (scripts, tests) keeps the blocking variant.
    """

    def ask(args: dict[str, Any]) -> tuple[str, dict]:
        response = pipeline_provider().query_sync(top_k=3, **args)
        return _format_rag_response(response), rag_artifact(response)

    async def aask(args: dict[str, Any]) -> tuple[str, dict]:
        pipeline = await asyncio.to_thread(pipeline_provider)  # the first call builds it
        response = await pipeline.aquery(top_k=3, **args)
        return _format_rag_response(response), rag_artifact(response)

    @tool(response_format="content_and_artifact")
    def search_ev_knowledge(
        query: str,
        model: str = "",
        category: str = "",
    ) -> tuple[str, dict]:
        """Tìm kiếm thông tin kỹ thuật, bảo dưỡng, bảo hành, bảng giá trong Cẩm nang xe điện VinFast trên Qdrant Cloud.

        Args:
            query: Câu hỏi hoặc từ khóa cần tra cứu (ví dụ: 'chính sách bảo hành pin', 'chi phí bảo dưỡng mốc 24.000 km')
            model: Dòng xe cần tra cứu (tùy chọn: 'VF3', 'VF5', 'VF6', 'VF7', 'VF8', 'VF9', 'VFe34', 'ALL')
            category: Phân loại thông tin (tùy chọn: 'maintenance', 'warranty', 'pricing', 'battery', 'procedure')

        Returns:
            Câu trả lời chính xác có nguồn dẫn chính hãng
        """
        return ask(_search_args(query, model, category))

    async def asearch_ev_knowledge(query: str, model: str = "", category: str = "") -> tuple[str, dict]:
        return await aask(_search_args(query, model, category))

    @tool(response_format="content_and_artifact")
    def get_maintenance_schedule_rag(model: str, km: int) -> tuple[str, dict]:
        """Tra cứu các hạng mục bảo dưỡng định kỳ theo dòng xe và số km từ cẩm nang chính hãng.

        Args:
            model: Tên dòng xe điện (ví dụ: 'VF5', 'VF6', 'VF8', 'VFe34')
            km: Số km hiện tại hoặc mốc km cần bảo dưỡng (ví dụ: 12000, 24000, 48000)

        Returns:
            Danh sách hạng mục bảo dưỡng chi tiết và lưu ý kỹ thuật
        """
        return ask(_maintenance_args(model, km))

    async def aget_maintenance_schedule_rag(model: str, km: int) -> tuple[str, dict]:
        return await aask(_maintenance_args(model, km))

    @tool(response_format="content_and_artifact")
    def get_warranty_policy_rag(model: str, component: str = "") -> tuple[str, dict]:
        """Tra cứu chính sách, điều kiện và các trường hợp loại trừ bảo hành chính hãng từ VinFast.

        Args:
            model: Tên dòng xe điện (ví dụ: 'VF8', 'VF9', 'VF5', 'VFe34')
            component: Bộ phận cần tra cứu (ví dụ: 'pin', 'động cơ', 'khung gầm', 'ắc quy 12V', 'màn hình')

        Returns:
            Chính sách bảo hành, thời hạn năm, số km tối đa và điều kiện áp dụng
        """
        return ask(_warranty_args(model, component))

    async def aget_warranty_policy_rag(model: str, component: str = "") -> tuple[str, dict]:
        return await aask(_warranty_args(model, component))

    search_ev_knowledge.coroutine = asearch_ev_knowledge
    get_maintenance_schedule_rag.coroutine = aget_maintenance_schedule_rag
    get_warranty_policy_rag.coroutine = aget_warranty_policy_rag
    return [search_ev_knowledge, get_maintenance_schedule_rag, get_warranty_policy_rag]


search_ev_knowledge, get_maintenance_schedule_rag, get_warranty_policy_rag = build_rag_tools(_get_rag_pipeline)
