from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgentState
from src.agents.tools.RAG.query.rag_tool import _get_rag_pipeline
from src.agents.tools.RAG.query.schemas import UserVehicleContext

logger = logging.getLogger(__name__)


async def rag_retrieval_node(state: AgentState) -> dict[str, Any]:
    """Node thực thi tra cứu tài liệu kỹ thuật xe điện trên Qdrant Cloud.

    Đọc state: query, vehicle_model, current_odometer_km
    Ghi vào state: response, citations, confidence, fallback_required
    """
    query = state.get("query", "").strip()
    if not query:
        return {"error": "Câu truy vấn rỗng."}

    model = state.get("vehicle_model")
    odo = state.get("current_odometer_km")

    vehicle_context = UserVehicleContext(model=model, current_odometer_km=odo) if model else None

    try:
        pipeline = _get_rag_pipeline()
        rag_response = await pipeline.query(
            query=query,
            vehicle_context=vehicle_context,
            top_k=4,
        )

        citations_data = [c.model_dump() for c in rag_response.citations]

        return {
            "response": rag_response.answer,
            "citations": citations_data,
            "confidence": rag_response.confidence,
            "fallback_required": rag_response.fallback_required,
            "metadata": rag_response.metadata,
        }
    except Exception as e:
        logger.error(f"Lỗi khi thực thi RAG node: {e}")
        return {
            "error": str(e),
            "response": "Xin lỗi, hiện tại hệ thống tra cứu kỹ thuật đang bận. Quý khách vui lòng thử lại sau.",
            "fallback_required": True,
        }
