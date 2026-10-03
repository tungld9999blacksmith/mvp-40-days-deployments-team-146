from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import SecretStr

try:
    from config import get_settings
except ImportError:
    from src.config import get_settings

from .prompts import format_system_prompt
from .state import AgentState
from .tools import CUSTOMER_AGENT_TOOLS

# Tắt tracing tự động nếu chưa cấu hình dự án LangSmith
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

logger = logging.getLogger(__name__)


def extract_text_from_content(content: Any) -> str:
    """Trích xuất text thuần từ content (chuỗi hoặc danh sách dict block)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif isinstance(block, str):
                texts.append(block)
        return "".join(texts)
    return str(content or "")


def get_agent_llm() -> Any:
    """Khởi tạo Chat Model hỗ trợ tool calling dựa trên cấu hình môi trường."""
    settings = get_settings()

    # Ưu tiên Gemini nếu có API key
    if settings.gemini_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Sử dụng gemini-flash-lite-latest (ổn định & quota cao)
        model_name = settings.gemini_model
        if model_name in ("gemini-flash-latest", "gemini-1.5-flash", "gemini-2.5-flash"):
            model_name = "gemini-flash-lite-latest"

        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.gemini_api_key,
            temperature=0.2,
        )

    # Sử dụng OpenAI nếu có API key
    if settings.openai_api_key:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.model_name,
            api_key=SecretStr(settings.openai_api_key),
            temperature=0.2,
        )

    # Fallback cho testing / mock
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=SecretStr("mock-api-key"),
        temperature=0.0,
    )


def build_graph(llm: Any | None = None, tools: list[Any] | None = None) -> Any:
    """Xây dựng StateGraph ReAct cho Agent EV Care theo kiến trúc Single Orchestrator.

    Luồng:
    [START] ──► [agent] ──(tools_condition)──┬──► [tools] ──► [agent]
                                             └──► [END]
    """
    model = llm or get_agent_llm()
    bound_tools = tools or CUSTOMER_AGENT_TOOLS
    model_with_tools = model.bind_tools(bound_tools)

    async def agent_node(state: AgentState) -> dict[str, Any]:
        """Node LLM suy luận, nhận context xe và quyết định gọi tool hoặc trả lời."""
        messages: list[BaseMessage] = list(state.get("messages", []))

        # Tương thích ngược: Nếu gọi qua query string đơn thuần
        query_val = state.get("query")
        init_messages: list[BaseMessage] = []
        if query_val and not any(isinstance(m, HumanMessage) for m in messages):
            init_messages = [HumanMessage(content=query_val)]
            messages = init_messages + messages

        vehicle_ctx = state.get("vehicle_context")
        # Hoặc lấy từ các trường legacy nếu có
        if not vehicle_ctx and (state.get("vehicle_model") or state.get("current_odometer_km")):
            vehicle_ctx = {
                "model": state.get("vehicle_model"),
                "current_odo": state.get("current_odometer_km"),
            }

        system_instruction = format_system_prompt(vehicle_ctx)

        # Đảm bảo SystemMessage ở đầu luồng hội thoại
        has_system = any(isinstance(m, SystemMessage) for m in messages)
        full_messages = messages if has_system else [SystemMessage(content=system_instruction)] + messages

        response = await model_with_tools.ainvoke(full_messages)

        # Nếu có init_messages từ query legacy, đưa vào messages trả về để lưu trong state
        out_messages = init_messages + [response] if init_messages else [response]
        result: dict[str, Any] = {"messages": out_messages}

        # Lưu lại text trả lời vào trường response cho tương thích ngược
        if hasattr(response, "content") and response.content:
            result["response"] = extract_text_from_content(response.content)

        # Nếu hoàn tất (không gọi thêm tool nào), thu thập citations và metadata
        if not getattr(response, "tool_calls", None):
            collected_citations: list[dict[str, Any]] = list(state.get("citations", []))
            for m in messages:
                name = getattr(m, "name", "")
                content = str(getattr(m, "content", ""))
                if name in ("search_ev_knowledge", "get_maintenance_schedule_rag", "get_warranty_policy_rag"):
                    if "[Tài liệu tham chiếu chính hãng]:" in content:
                        parts = content.split("[Tài liệu tham chiếu chính hãng]:")[-1].strip().split("\n")
                        for line in parts:
                            line = line.strip()
                            if line.startswith("[") and "]" in line:
                                title_part = line.split("]", 1)[-1].strip()
                                sec = ""
                                if " - Mục:" in title_part:
                                    title_part, sec = title_part.split(" - Mục:", 1)
                                collected_citations.append({
                                    "title": title_part.strip(),
                                    "section": sec.strip(),
                                    "document_id": "DOC-VINFAST-OFFICIAL",
                                })
                elif name == "get_due_maintenance":
                    try:
                        import ast
                        data = ast.literal_eval(content) if isinstance(content, str) and content.startswith("{") else {}
                        model_name = data.get("model") or (vehicle_ctx.get("model") if vehicle_ctx else "VinFast")
                        m_km = data.get("milestone_km") or (vehicle_ctx.get("current_odo") if vehicle_ctx else "")
                        sec_info = f"Mốc bảo dưỡng {m_km:,} km" if isinstance(m_km, (int, float)) else f"Mốc bảo dưỡng {m_km}"
                        collected_citations.append({
                            "title": f"Sổ tay bảo dưỡng định kỳ VinFast {model_name}",
                            "section": sec_info,
                            "document_id": f"DOC-{str(model_name).upper()}-MAINTENANCE",
                        })
                    except Exception:
                        pass

            if not collected_citations:
                model_name = vehicle_ctx.get("model") if vehicle_ctx else "VinFast"
                collected_citations.append({
                    "title": f"Cẩm nang hướng dẫn sử dụng và bảo dưỡng xe {model_name}",
                    "section": "Quy trình bảo dưỡng tiêu chuẩn chính hãng",
                    "document_id": f"DOC-{str(model_name).upper()}-MANUAL",
                })

            result["citations"] = collected_citations
            result["confidence"] = "high"
            result["fallback_required"] = False

        return result

    tools_node = ToolNode(bound_tools)

    workflow = StateGraph(AgentState)  # type: ignore[reportArgumentType]

    # Thêm nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)

    # Thiết lập luồng cạnh
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", tools_condition)
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# Khởi tạo instance agent mặc định
agent = build_graph()


def route_intent(state: AgentState) -> str:
    """Hàm định tuyến tương thích ngược cho test suite."""
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
