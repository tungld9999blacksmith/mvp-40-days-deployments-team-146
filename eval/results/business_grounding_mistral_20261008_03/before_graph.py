from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from pydantic import SecretStr

try:
    from config import get_settings
except ImportError:
    from src.config import get_settings

from .evidence import collect_rag_evidence
from .guardrails import guarded_calls, tool_failure
from .prompts import format_system_prompt
from .state import AgentState
from .tools import CUSTOMER_AGENT_TOOLS

# Tắt tracing tự động nếu chưa cấu hình dự án LangSmith
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

logger = logging.getLogger(__name__)


def prefill_due_maintenance_args(
    args: dict[str, Any], vehicle_ctx: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Bổ sung model/ODO/số tháng còn thiếu cho get_due_maintenance từ vehicle_context tin cậy.

    Trả về (args đã bổ sung, danh sách field được bổ sung). Dùng chung với
    tests/test_agents/evaluationLLM/benchmark_models.py để benchmark khớp production.
    """
    args = dict(args or {})
    patched: list[str] = []
    if not args.get("model") and vehicle_ctx.get("model"):
        args["model"] = vehicle_ctx["model"]
        patched.append("model")
    if not args.get("current_odometer_km") and not args.get("current_odo"):
        odo = vehicle_ctx.get("current_odo") or vehicle_ctx.get("current_odometer_km")
        if odo:
            args["current_odometer_km"] = int(odo)
            patched.append("current_odometer_km")
    if args.get("months_since_last_service") is None:
        months = vehicle_ctx.get("months_since_last") or vehicle_ctx.get("months_since_last_service")
        if months is not None:
            args["months_since_last_service"] = int(months)
            patched.append("months_since_last_service")
    return args, patched


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

    if settings.llm_provider == "openrouter":
        from langchain_openai import ChatOpenAI

        if not settings.openrouter_api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        endpoints = settings.openrouter_endpoints_for_stage("agent")
        routing = {"extra_body": {"provider": {"order": list(endpoints), "allow_fallbacks": True}}} if endpoints else {}
        return ChatOpenAI(
            model=settings.openrouter_model_for_stage("agent"),
            api_key=SecretStr(settings.openrouter_api_key),
            base_url=settings.openrouter_base_url,
            max_tokens=settings.openrouter_max_tokens,
            temperature=0.2,
            timeout=settings.chat_run_timeout_seconds,
            max_retries=1,
            **routing,
        )

    # Ưu tiên Gemini nếu có API key
    if settings.gemini_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Sử dụng gemini-flash-lite-latest (ổn định & quota cao)
        model_name = settings.gemini_model
        if model_name in ("gemini-flash-latest", "gemini-1.5-flash", "gemini-2.5-flash"):
            model_name = "gemini-flash-lite-latest"

        llm_kwargs: dict[str, Any] = {
            "model": model_name,
            "google_api_key": settings.gemini_api_key,
        }
        # Model dòng -lite sử dụng fixed sampling defaults từ Google, không truyền temperature để tránh cảnh báo UserWarning
        if "lite" not in model_name.lower():
            llm_kwargs["temperature"] = 0.2

        return ChatGoogleGenerativeAI(**llm_kwargs)

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


def get_checkpointer(use_postgres: bool = True) -> Any:
    """Return the open saver owned by API lifespan; offline graphs use memory."""
    from .checkpoint import current_checkpointer
    return current_checkpointer() if use_postgres else MemorySaver()


def build_graph(
    llm: Any | None = None,
    tools: list[Any] | None = None,
    checkpointer: Any | None = None,
    *,
    system_prompt: str | None = None,
    collect_citations: bool = True,
) -> Any:
    """Xây dựng StateGraph ReAct cho Agent EV Care theo kiến trúc Single Orchestrator.

    Luồng:
    [START] ──► [agent] ──(tools_condition)──┬──► [tools] ──► [agent]
                                             └──► [END]

    Args:
        llm: Chat model tùy chỉnh (mặc định: auto-detect từ env)
        tools: Danh sách tool tùy chỉnh (mặc định: CUSTOMER_AGENT_TOOLS)
        checkpointer: LangGraph checkpointer (mặc định: auto-detect PostgreSQL hoặc MemorySaver)
    """
    model = llm if llm is not None else get_agent_llm()
    bound_tools = tools if tools is not None else CUSTOMER_AGENT_TOOLS
    model_with_tools = model.bind_tools(bound_tools)
    maintenance_arg_names = next(
        (set(tool.args) for tool in bound_tools if getattr(tool, "name", "") == "get_due_maintenance"),
        set(),
    )

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

        system_instruction = system_prompt or format_system_prompt(vehicle_ctx)
        if system_prompt and vehicle_ctx:
            import json

            system_instruction += "\nNgữ cảnh xe được backend xác thực: " + json.dumps(vehicle_ctx, ensure_ascii=False)

        # Đảm bảo SystemMessage ở đầu luồng hội thoại
        has_system = any(isinstance(m, SystemMessage) for m in messages)
        full_messages = messages if has_system else [SystemMessage(content=system_instruction)] + messages

        response = await model_with_tools.ainvoke(full_messages)

        # --- Task #2: Pre-fill args cho get_due_maintenance từ vehicle_context ---
        # LLM đôi khi bỏ sót model/ODO khi context đã rõ; inject tự động để tránh tool fail.
        if getattr(response, "tool_calls", None) and vehicle_ctx:
            patched_tool_calls = []
            changed = False
            for tc in response.tool_calls:
                if tc.get("name") == "get_due_maintenance" and maintenance_arg_names:
                    args, patched = prefill_due_maintenance_args(tc.get("args", {}), vehicle_ctx)
                    # Main's current tool has no model/ODO inputs: it reads its
                    # verified caller and selected vehicle from the database.
                    # Only add fields declared by a legacy tool's public schema.
                    original_args = dict(tc.get("args", {}))
                    args = {**original_args, **{
                        key: args[key] for key in patched if key in maintenance_arg_names
                    }}
                    patched = [key for key in patched if key in maintenance_arg_names]
                    changed = changed or bool(patched)
                    patched_tool_calls.append({**tc, "args": args})
                else:
                    patched_tool_calls.append(tc)
            if changed:
                # Gắn lại tool_calls đã patch vào response — dùng copy để tránh mutate object LangChain
                try:
                    response = response.model_copy(update={"tool_calls": patched_tool_calls})
                except Exception:
                    pass  # Nếu không patch được, giữ nguyên — LLM args vẫn được dùng

        # Nếu có init_messages từ query legacy, đưa vào messages trả về để lưu trong state
        response = guarded_calls(response, messages, bound_tools)

        out_messages = init_messages + [response] if init_messages else [response]
        result: dict[str, Any] = {"messages": out_messages}

        # Lưu lại text trả lời vào trường response cho tương thích ngược
        if hasattr(response, "content") and response.content:
            result["response"] = extract_text_from_content(response.content)

        # Nếu hoàn tất (không gọi thêm tool nào), thu thập citations từ tool messages thật
        if collect_citations and not getattr(response, "tool_calls", None):
            result.update(collect_rag_evidence(messages))

        return result

    tools_node = ToolNode(bound_tools, handle_tool_errors=True)

    async def tool_error_node(state: AgentState) -> dict[str, Any]:
        from langchain_core.messages import AIMessage
        messages = list(state.get("messages", []))
        answer = tool_failure(messages) or "Chưa có kết quả đã xác minh cho yêu cầu này."
        result = {"messages": [AIMessage(content=answer)], "response": answer}
        if collect_citations:
            result.update(collect_rag_evidence(messages))
        return result


    def hitl_routing(state: AgentState) -> str:
        """Kiểm tra xem LLM có muốn gọi create_booking_draft không.
        Nếu có → chuyển sang hitl_node để xin xác nhận từ user trước.
        Nếu không → chuyển sang tools_node bình thường.
        """
        messages = state.get("messages", [])
        if not messages:
            return "end"
        last = messages[-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        has_booking = any(tc.get("name") == "create_booking_draft" for tc in tool_calls)
        if has_booking:
            return "hitl"
        if tool_calls:
            return "tools"
        return "end"

    async def hitl_node(state: AgentState) -> dict[str, Any]:
        """Human-in-the-Loop node: tạm dừng graph, chờ chủ xe xác nhận.

        Gọi interrupt() để LangGraph lưu checkpoint và trả quyền kiểm soát về orchestrator.
        Orchestrator sẽ emit sự kiện 'hitl_required' cho frontend, rồi resume graph
        khi user xác nhận hoặc hủy thông qua confirm_booking_turn().
        """
        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        tool_calls = getattr(last, "tool_calls", None) or []

        # Trích thông tin booking draft để gửi lên frontend
        booking_draft: dict[str, Any] = {}
        for tc in tool_calls:
            if tc.get("name") == "create_booking_draft":
                booking_draft = tc.get("args", {})
                break

        # interrupt() lưu state vào checkpointer và raise exception đặc biệt của LangGraph
        # Giá trị trả về là dữ liệu mà orchestrator truyền vào khi resume (confirmed / rejected)
        user_decision: dict[str, Any] = interrupt(
            {
                "type": "booking_confirmation_required",
                "draft": booking_draft,
            }
        )

        # Nếu user từ chối → xóa tool_call booking khỏi messages, trả thông báo hủy
        if not user_decision.get("confirmed", False):
            from langchain_core.messages import AIMessage

            cancel_msg = AIMessage(
                content="Đã hủy yêu cầu đặt lịch theo ý bạn. Bạn có muốn chọn khung giờ khác hoặc xưởng khác không?",
            )
            return {"messages": [cancel_msg], "draft_booking": None}

        # Nếu user xác nhận → tiếp tục, graph sẽ tự route sang tools_node để thực thi create_booking_draft
        return {}

    workflow = StateGraph(AgentState)  # type: ignore[reportArgumentType]

    # Thêm nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("tool_error", tool_error_node)
    workflow.add_node("hitl", hitl_node)

    # Luồng chính: START → agent → (routing) → tools/hitl/end
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        hitl_routing,
        {"tools": "tools", "hitl": "hitl", "end": "__end__"},
    )
    # Sau HITL (user xác nhận) → tools để thực thi create_booking_draft
    workflow.add_conditional_edges(
        "hitl",
        lambda state: (
            "tools" if state.get("messages") and getattr(state["messages"][-1], "tool_calls", None) else "agent"
        ),
        {"tools": "tools", "agent": "agent"},
    )
    workflow.add_conditional_edges(
        "tools", lambda state: "tool_error" if tool_failure(list(state.get("messages", []))) else "agent",
        {"tool_error": "tool_error", "agent": "agent"},
    )
    workflow.add_edge("tool_error", "__end__")

    # Compile với checkpointer — dùng checkpointer truyền vào, hoặc auto-detect
    cp = checkpointer if checkpointer is not None else get_checkpointer()
    return workflow.compile(checkpointer=cp)


def __getattr__(name: str) -> Any:
    """Keep the legacy ``graph.agent`` export lazy, using the DI graph."""
    if name == "agent":
        from .dependency import get_agent_graph

        return get_agent_graph()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
