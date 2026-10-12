from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import SecretStr

try:
    from config import get_settings
except ImportError:
    from src.config import get_settings

from ..infrastructure.observability import instrument_tools, step
from .evidence import collect_rag_evidence, preserve_rag_fallback
from .guardrails import guarded_calls, tool_failure
from .prompts import format_system_prompt
from .state import AgentState
from .telemetry import record_tool_call_guard, tool_call_signature
from .tools import CUSTOMER_AGENT_TOOLS

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


def _is_upstream_error(response: Any) -> bool:
    """An empty reply the provider ended with finish_reason="error" (not a real answer)."""
    metadata = getattr(response, "response_metadata", None) or {}
    return (
        metadata.get("finish_reason") == "error"
        and not getattr(response, "tool_calls", None)
        and not extract_text_from_content(getattr(response, "content", "")).strip()
    )


def get_agent_llm(*, fallback: bool = False) -> Any:
    """Khởi tạo Chat Model hỗ trợ tool calling dựa trên cấu hình môi trường."""
    settings = get_settings()
    from src.infrastructure.llm.routing import fallback_provider, settings_for_stage

    settings = (
        settings.model_copy(update={"llm_provider": settings.llm_fallback_provider})
        if fallback else settings_for_stage(settings, "orchestrator")
    )
    # The primary must fail fast so the fallback still fits in the chat turn deadline.
    max_retries = 0 if not fallback and fallback_provider(settings) else 1

    if settings.llm_provider == "openrouter":
        from src.infrastructure.llm.openrouter_chat import OpenRouterChatOpenAI

        if not settings.openrouter_api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        endpoints = settings.openrouter_endpoints_for_stage("agent")
        routing = {"extra_body": {"provider": {"allow_fallbacks": True, **({"order": list(endpoints)} if endpoints else {})}}}
        return OpenRouterChatOpenAI(
            model=settings.openrouter_model,
            api_key=SecretStr(settings.openrouter_api_key),
            base_url=settings.openrouter_base_url,
            max_tokens=settings.openrouter_max_tokens,
            temperature=0.2,
            timeout=settings.llm_call_timeout_seconds,
            max_retries=0,
            # Usage in the final stream chunk: LangSmith counts tokens / cost of streamed turns.
            stream_usage=True,
            **routing,
        )

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        model_name = settings.gemini_model
        if not settings.gemini_api_key.strip():
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")

        llm_kwargs: dict[str, Any] = {
            "model": model_name,
            "google_api_key": settings.gemini_api_key,
            "timeout": settings.llm_call_timeout_seconds,
            "max_retries": max_retries,
        }
        # Model dòng -lite sử dụng fixed sampling defaults từ Google, không truyền temperature để tránh cảnh báo UserWarning
        if "lite" not in model_name.lower():
            llm_kwargs["temperature"] = 0.2

        return ChatGoogleGenerativeAI(**llm_kwargs)

    if settings.llm_provider == "openai" and settings.openai_api_key:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.model_name,
            api_key=SecretStr(settings.openai_api_key),
            temperature=0.2,
            timeout=settings.llm_call_timeout_seconds,
            max_retries=max_retries,
            stream_usage=True,
        )

    raise ValueError(f"Agent provider {settings.llm_provider!r} is unsupported or missing its API key")


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
    use_llm_fallback: bool = False,
    tool_call_reviewer: Any | None = None,
    memory_settings: Any | None = None,
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
    # Grafana-side spans + tool metrics around each tool body (idempotent).
    bound_tools = instrument_tools(tools if tools is not None else CUSTOMER_AGENT_TOOLS)
    model_with_tools = model.bind_tools(bound_tools)
    settings = get_settings()
    memory_config = memory_settings if memory_settings is not None else settings
    if llm is None and tool_call_reviewer is None and settings.llm_booking_check_enabled:
        from .tool_review import review_tool_call

        tool_call_reviewer = review_tool_call
    if (llm is None or use_llm_fallback) and settings.llm_fallback_provider:
        from openai import APIConnectionError, InternalServerError, RateLimitError

        from src.infrastructure.llm.routing import fallback_provider, settings_for_stage

        if fallback_provider(settings_for_stage(settings, "orchestrator")):
            model_with_tools = model_with_tools.with_fallbacks(
                [get_agent_llm(fallback=True).bind_tools(bound_tools)],
                exceptions_to_handle=(APIConnectionError, InternalServerError, RateLimitError),
            )
    maintenance_arg_names = next(
        (set(tool.args) for tool in bound_tools if getattr(tool, "name", "") == "get_due_maintenance"),
        set(),
    )

    async def agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
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

        # Per-turn recall is deliberately excluded from checkpoint state and metadata.
        preferences = config.get("configurable", {}).get("__memory_preferences", [])
        if any(getattr(tool, "name", "") == "remember_preference" for tool in bound_tools):
            from .memory_guard import current_preference_choice, verified_preference_recall

            # Pure preference reads/one-time repetitions need no model or business
            # tools. Resolve before the model can invent a key or choose a tool.
            direct = verified_preference_recall(AIMessage(content=""), messages, preferences)
            direct = current_preference_choice(direct, messages)
            if direct.content:
                return {"messages": init_messages + [direct], "response": direct.content, "citations": []}
        if memory_config.agent_memory_context_mode != "off" or state.get("memory_summary") or preferences:
            from .memory_context import build_memory_context

            try:
                bounded = build_memory_context(messages, system_instruction, memory_config,
                    summary=state.get("memory_summary"), preferences=preferences, tools=bound_tools)
            except ValueError:
                if memory_config.agent_memory_context_mode != "shadow" or state.get("memory_summary") or preferences:
                    raise
                logger.info("agent_memory_shadow_context_over_budget")
                bounded = None
            if memory_config.agent_memory_context_mode != "shadow" or state.get("memory_summary") or preferences:
                full_messages = bounded.messages

        response = await model_with_tools.ainvoke(full_messages)
        if _is_upstream_error(response):
            # OpenRouter ends with finish_reason="error" and no content when the provider fails
            # mid-answer. Nothing ran in this call, so one retry is safe.
            logger.warning("Agent LLM returned an upstream error; retrying once")
            response = await model_with_tools.ainvoke(full_messages)
        if _is_upstream_error(response):
            raise RuntimeError("Agent LLM returned an upstream error twice")

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
        with step("agent.guard.tool_calls", attributes={"guard.stage": "tool_calls"}) as guard:
            before = tool_call_signature(response)
            response = guarded_calls(response, messages, bound_tools)
            record_tool_call_guard(guard, before, response)
        response = preserve_rag_fallback(response, messages)
        from .memory_guard import verified_memory_response, verified_preference_recall
        response = verified_memory_response(response, messages)
        if any(getattr(tool, "name", "") == "remember_preference" for tool in bound_tools):
            response = verified_preference_recall(response, messages, preferences)

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


    async def guarded_tools_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        from langchain_core.messages import ToolMessage

        from .tool_review import SENSITIVE_TOOL_NAMES

        if tool_call_reviewer is None:
            return await tools_node.ainvoke(state, config)
        last = state["messages"][-1]
        accepted, rejected = [], []
        for call in last.tool_calls:
            if call["name"] not in SENSITIVE_TOOL_NAMES or await tool_call_reviewer(state["messages"], call):
                accepted.append(call)
            else:
                rejected.append(ToolMessage(
                    content='{"status":"error","code":"TOOL_REVIEW_REJECTED","message":"Yêu cầu chưa đủ căn cứ để thực hiện. Vui lòng làm rõ lựa chọn hoặc yêu cầu thay đổi."}',
                    tool_call_id=call["id"], name=call["name"],
                ))
        outputs = []
        if accepted:
            execution_state = {**state, "messages": [*state["messages"][:-1], last.model_copy(update={"tool_calls": accepted})]}
            result = await tools_node.ainvoke(execution_state, config)
            outputs = result["messages"]
        return {"messages": outputs + rejected}

    def agent_routing(state: AgentState) -> str:
        """Run requested tools or finish the turn.

        Booking HITL is owned by the proposal card and API-QB-02. The graph
        never pauses before ``propose_booking`` because that tool performs no
        booking write and does not reserve a slot.
        """
        messages = state.get("messages", [])
        if not messages:
            return "end"
        last = messages[-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        return "tools" if tool_calls else "end"

    workflow = StateGraph(AgentState)  # type: ignore[reportArgumentType]

    # Thêm nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", guarded_tools_node)
    workflow.add_node("tool_error", tool_error_node)

    # Luồng chính: START → agent → tools/end. Booking confirmation is API-QB-02.
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        agent_routing,
        {"tools": "tools", "end": "__end__"},
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
