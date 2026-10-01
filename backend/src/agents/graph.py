from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from .nodes import analyze_node, rag_retrieval_node, respond_node
from .state import AgentState


def route_intent(state: AgentState) -> str:
    """Điều hướng luồng xử lý: Phân biệt câu hỏi tra cứu kiến thức RAG và hội thoại chung."""
    if state.get("error"):
        return END

    query = state.get("query", "").lower()
    rag_keywords = [
        "bảo dưỡng",
        "bảo hành",
        "pin",
        "ắc quy",
        "lịch",
        "chi phí",
        "giá",
        "km",
        "mốc",
        "hỏng",
        "thay",
        "lọc",
        "phanh",
        "dầu",
        "vf",
        "vinfast",
        "kỹ thuật",
        "chính sách",
    ]

    if any(k in query for k in rag_keywords):
        return "rag_retrieval"

    return "respond"


def build_graph() -> Any:
    """Xây dựng StateGraph cho Agent EV Care."""
    graph = StateGraph(AgentState)

    # Thêm nodes
    graph.add_node("analyze", analyze_node)
    graph.add_node("rag_retrieval", rag_retrieval_node)
    graph.add_node("respond", respond_node)

    # Thiết lập cạnh (edges)
    graph.set_entry_point("analyze")
    graph.add_conditional_edges(
        "analyze",
        route_intent,
        {
            "rag_retrieval": "rag_retrieval",
            "respond": "respond",
            END: END,
        },
    )
    graph.add_edge("rag_retrieval", END)
    graph.add_edge("respond", END)

    return graph.compile()


agent = build_graph()
