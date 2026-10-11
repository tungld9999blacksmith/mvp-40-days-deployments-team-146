"""Paid memory smoke test in isolated SQLite; production prompt/tool schemas.

Only memory tools execute. Other tools return an explicit sandbox error. No
embedding, model judge, production database, Firebase or HTTP/UI traffic.
Each model request reserves a conservative UTF-8 byte ceiling before sending.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

# Set isolation BEFORE importing services that construct the database engine.
if __name__ == "__main__":
    os.environ.update(
        APP_ENV="test", DATABASE_URL="sqlite://", LANGCHAIN_TRACING_V2="false",
        AGENT_MEMORY_CONTEXT_MODE="on", AGENT_MEMORY_READ_ENABLED="true",
        AGENT_MEMORY_WRITE_ENABLED="true",
    )
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr
from sqlalchemy import func
from sqlmodel import Session, select

from src.agents.checkpoint import selector_loop_factory
from src.agents.graph import build_graph, extract_text_from_content, get_agent_llm
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from src.agents.tools.memory_tools import build_memory_tools
from src.common.core.conversation import ChatMessage, Conversation, MessageRole
from src.common.core.conversation.memory import AgentUserMemory
from src.config import get_settings
from src.modules.agent_memory.preferences import PreferenceService, normalized
from src.modules.agent_memory.summary import SummaryService
from tests._maintenance import add_workshop
from tests._user_vehicle import add_owner, add_vehicle, make_session


class BudgetExceeded(RuntimeError):
    pass


class BudgetLedger:
    def __init__(self, limit, input_rate, output_rate, max_calls=32):
        self.limit, self.input_rate, self.output_rate = limit, input_rate, output_rate
        self.max_calls, self.calls, self.case = max_calls, [], None
        self.stop = False

    @property
    def spent(self):
        return sum(c["budget_charge_usd"] for c in self.calls)

    def reserve(self, messages, tools, output_tokens):
        # Byte count bounds ordinary text tokens conservatively. Include role,
        # tool-call framing, schemas and a further 4096-token safety allowance.
        payload = {
            "messages": [m.model_dump(exclude={"response_metadata", "usage_metadata"}) for m in messages],
            "tools": tools,
        }
        ceiling = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")) + 4096
        reserve = ceiling * self.input_rate + output_tokens * self.output_rate
        if self.stop or len(self.calls) >= self.max_calls or self.spent + reserve > self.limit:
            raise BudgetExceeded("Next request cannot fit within the reserved budget")
        call = {
            "case": self.case, "reserved_usd": reserve, "budget_charge_usd": reserve,
            "provider_cost_usd": None, "input_tokens": None, "output_tokens": None,
            "status": "pending",
        }
        self.calls.append(call)
        return call

    def settle(self, call, result):
        message = result.generations[0].message
        usage = message.usage_metadata or {}
        # ChatOpenAI attaches llm_output metadata to messages AFTER _agenerate.
        provider_usage = ((message.response_metadata or {}).get("token_usage")
                          or (result.llm_output or {}).get("token_usage") or {})
        cost = provider_usage.get("cost")
        if not isinstance(cost, (int, float)):
            cost = ((result.llm_output or {}).get("token_usage") or {}).get("cost")
        call.update(
            input_tokens=usage.get("input_tokens", provider_usage.get("prompt_tokens")),
            output_tokens=usage.get("output_tokens", provider_usage.get("completion_tokens")),
            provider_cost_usd=cost if isinstance(cost, (int, float)) else None,
            status="completed",
        )
        if call["input_tokens"] is not None and call["output_tokens"] is not None:
            estimate = call["input_tokens"] * self.input_rate + call["output_tokens"] * self.output_rate
            call["no_cache_estimate_usd"] = estimate
            call["budget_charge_usd"] = max(estimate, call["provider_cost_usd"] or 0)
        elif call["provider_cost_usd"] is not None:
            call["budget_charge_usd"] = call["provider_cost_usd"]
        else:
            self.stop = True  # Unknown billing retains the entire reservation.
        if call["budget_charge_usd"] > call["reserved_usd"]:
            self.stop = True


class BudgetedChatOpenAI(ChatOpenAI):
    _ledger: BudgetLedger = PrivateAttr()

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        call = self._ledger.reserve(messages, kwargs.get("tools", []), self.max_tokens)
        try:
            result = await super()._agenerate(messages, stop, run_manager, **kwargs)
        except BaseException as exc:
            call.update(status="error", error_type=type(exc).__name__)
            self._ledger.stop = True  # Stop on unknown fees/provider failures.
            raise
        self._ledger.settle(call, result)
        return result


def sandbox_tools(open_session):
    real_memory = {t.name: t for t in build_memory_tools(SimpleNamespace(open_session=open_session))}

    def blocked(**kwargs):
        return {"status": "ERROR", "code": "EVALUATION_SANDBOX", "message": "Non-memory services are not enabled in this evaluation."}

    return [
        real_memory[t.name] if t.name in real_memory else t.model_copy(update={"func": blocked, "coroutine": None})
        for t in CUSTOMER_AGENT_TOOLS
    ]


def add_message(db, conversation_id, content, role=MessageRole.USER):
    seq = (db.exec(select(func.max(ChatMessage.seq))).one() or 0) + 1
    row = ChatMessage(conversation_id=conversation_id, seq=seq, role=role, content=content)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def new_conversation(db, owner, vehicle):
    row = Conversation(user_id=owner.user_id, user_vehicle_id=vehicle.id, last_message_at=datetime.now(UTC))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def window_answer(answer, day="thu bay", period="chieu"):
    text = normalized(answer)
    return day in text and period in text


def itemized_answer(answer):
    return any(s in normalized(answer) for s in ("hang muc", "itemized", "chi tiet"))


def unavailable_answer(answer):
    """Absence can be followed by options/examples, without claiming a preference."""
    text = normalized(answer)
    return any(s in text for s in ("chua luu", "chua co", "khong co", "khong con", "chua ghi nho", "chua duoc ghi nho"))


def claims_memory_save(answer):
    text = normalized(answer)
    return any(s in text for s in ("toi da ghi nho", "minh da ghi nho", "toi da luu", "minh da luu"))


class Evaluation:
    def __init__(self, db, engine, llm, ledger, output, prior_cost=0, focus=False):
        self.db, self.engine, self.llm, self.ledger, self.output = db, engine, llm, ledger, output
        self.settings = get_settings()
        self.results = []
        self.long_context = []
        self.status = "running"
        self.prior_cost = prior_cost
        self.focus = focus

        @contextmanager
        def open_session():
            with Session(engine) as session:
                yield session

        self.tools = sandbox_tools(open_session)

    def flush(self):
        calls = self.ledger.calls
        costs = [c["provider_cost_usd"] for c in calls]
        durations = sorted(r["duration_ms"] for r in self.results if r["responded"])
        report = {
            "created_at": datetime.now(UTC).isoformat(), "status": self.status,
            "model": self.llm.model_name, "endpoint": "mistral/us", "budget_usd": self.ledger.limit + self.prior_cost,
            "prior_accounted_usd": self.prior_cost,
            "focus": self.focus,
            "combined_accounted_usd": self.ledger.spent + self.prior_cost,
            "budget_accounted_usd": self.ledger.spent,
            "provider_cost_usd": sum(costs) if costs and all(c is not None for c in costs) else None,
            "llm_calls": len(calls), "case_count": len(self.results),
            "passed": sum(r["passed"] for r in self.results),
            "responded": sum(r["responded"] for r in self.results),
            "graph_p50_ms": statistics.median(durations) if durations else None,
            "graph_p95_ms": durations[min(len(durations)-1, int(len(durations)*.95))] if durations else None,
            "method": "Natural text; production system prompt and all tool schemas; actual memory tools and services; deterministic assertions. Independent new threads reload SQL preferences. Pure preference recall is grounded/rendered from the authorized SQL projection; summary goal recall still uses the LLM. Scores measure final pipeline output, not raw model accuracy.",
            "limitations": ["SQLite with PostgreSQL-compatible test metadata, not production PostgreSQL", "MemorySaver, not process-restart PostgreSQL persistence", "Non-memory tools explicitly blocked; no business execution or live Firebase/HTTP/UI", "UTF-8 byte reservations include framing margin; actual fees from provider; unknown fees retain reservation and halt"],
            "cases": self.results, "calls": calls, "long_context": self.long_context,
        }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    async def turn(self, name, owner, vehicle, question, grader, *, conversation=None, history=None, summary=None, baseline=False):
        if self.focus and name not in {
            "save_window", "recall_window_new_thread", "current_window_override",
            "current_cost_override", "one_time_no_consent", "negated_consent",
        }:
            return
        self.ledger.case = name
        conversation = conversation or new_conversation(self.db, owner, vehicle)
        source = add_message(self.db, conversation.id, question)
        preferences = PreferenceService(self.db, self.settings).recall(owner.user_id, vehicle.id)
        config = {"configurable": {
            "thread_id": str(conversation.id), "user_id": owner.user_id,
            "user_vehicle_id": str(vehicle.id), "conversation_id": str(conversation.id),
            "source_message_id": str(source.id), "__memory_preferences": [] if baseline else preferences,
        }, "recursion_limit": 10}
        settings = self.settings.model_copy(update={"agent_memory_context_mode": "off"}) if baseline else self.settings
        # Each graph gets a fresh saver; recall must therefore come from SQL.
        graph = build_graph(self.llm, self.tools, MemorySaver(), memory_settings=settings)
        before = len(self.ledger.calls)
        started = time.perf_counter()
        row = {"name": name, "passed": False, "responded": False, "recalled_keys": [p["key"] for p in preferences]}
        try:
            state = await asyncio.wait_for(graph.ainvoke({
                "messages": [*(history or []), HumanMessage(content=question, id=str(source.id))],
                "memory_summary": summary or {},
                "vehicle_context": {"vehicle_id": str(vehicle.id), "model": "VF6"},
            }, config), timeout=60)
            answer = extract_text_from_content(state["messages"][-1].content)
            tool_results = [json.loads(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]
            tool_names = [m.name for m in state["messages"] if isinstance(m, ToolMessage)]
            self.db.expire_all()
            active = PreferenceService(self.db, self.settings).recall(owner.user_id, vehicle.id)
            passed = grader(answer, active, tool_results)
            # A sandbox-blocked tool is an execution failure, not a recall pass.
            passed = passed and not any(t.get("code") == "EVALUATION_SANDBOX" for t in tool_results)
            row.update(passed=bool(passed), responded=True, answer=answer, tools=tool_names,
                       answer_origin=("authorized_preference_projection" if state["messages"][-1].response_metadata.get("memory_recall_grounded")
                                      else "current_user_choice" if state["messages"][-1].response_metadata.get("memory_current_choice_grounded")
                                      else "model_or_existing_tool_guard"),
                       tool_statuses=[t.get("status") for t in tool_results],
                       tool_errors=[{"code": t.get("code"), "message": t.get("message")} for t in tool_results if t.get("status") == "ERROR"],
                       requests=[tc for m in state["messages"] if isinstance(m, AIMessage) for tc in m.tool_calls])
            add_message(self.db, conversation.id, answer or "[empty response]", MessageRole.ASSISTANT)
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            if isinstance(exc, BudgetExceeded):
                self.status = "stopped_budget"
            else:
                self.status = "stopped_error"
            self.ledger.stop = True
        row.update(duration_ms=round((time.perf_counter()-started)*1000), calls=len(self.ledger.calls)-before)
        self.results.append(row)
        self.flush()
        print(json.dumps({"case": name, "passed": row["passed"], "calls": row["calls"], "budget_accounted_usd": round(self.ledger.spent, 8), "error_type": row.get("error_type")}), flush=True)
        if self.ledger.stop:
            raise BudgetExceeded("Evaluation stopped; partial report saved")

    async def run(self):
        owner = add_owner(self.db)
        vehicle = add_vehicle(self.db, owner)
        other = add_owner(self.db, uid="budget-other", email="budget-other@example.com")
        other_vehicle = add_vehicle(self.db, other, vin="BUDGET-OTHER", external_vehicle_id="BUDGET-OTHER")
        second_vehicle = add_vehicle(self.db, owner, vin="BUDGET-SECOND", external_vehicle_id="BUDGET-SECOND")
        workshop = add_workshop(self.db, name="Memory Test Workshop")
        workshop_id = str(workshop.id)

        def has_key(preferences, key, value=None):
            return any(p["key"] == key and (value is None or p["value"] == value) for p in preferences)

        saves = [
            ("save_window", "Hãy nhớ tôi thích chiều thứ Bảy.", "preferred_service_window", {"day": "saturday", "period": "afternoon"}),
            ("save_cost", "Hãy nhớ tôi muốn xem chi phí theo từng hạng mục.", "cost_display_preference", {"format": "itemized"}),
            ("save_workshop", f"Hãy nhớ tôi ưu tiên xưởng có UUID {workshop_id}.", "preferred_workshop_id", {"workshop_id": workshop_id}),
        ]
        for name, question, key, value in saves:
            if self.focus and name != "save_window":
                conversation = new_conversation(self.db, owner, vehicle)
                source = add_message(self.db, conversation.id, question)
                PreferenceService(self.db, self.settings).remember(
                    owner.user_id, vehicle.id, conversation.id, source.id, key, value)
                continue
            await self.turn(name, owner, vehicle, question,
                            lambda a, p, t, k=key, v=value: has_key(p, k, v) and any(r.get("status") == "ok" and r.get("key") == k for r in t))
        await self.turn("recall_window_new_thread", owner, vehicle,
                        "Theo thông tin đã ghi nhớ, tôi thích ngày nào và buổi nào? Chỉ nhắc sở thích, không tra slot.",
                        lambda a, p, t: window_answer(a) and has_key(p, "preferred_service_window", saves[0][3]))
        await self.turn("recall_cost_new_thread", owner, vehicle,
                        "Theo thông tin đã ghi nhớ, tôi thích xem chi phí từng hạng mục hay chỉ tổng tiền? Không cần tra giá.",
                        lambda a, p, t: itemized_answer(a))
        await self.turn("recall_workshop_new_thread", owner, vehicle,
                        "UUID xưởng tôi đã yêu cầu ghi nhớ là gì? Chỉ nhắc UUID, không tra slot.",
                        lambda a, p, t: workshop_id in a)
        await self.turn("current_window_override", owner, vehicle,
                        "Lần này tôi chọn sáng Chủ nhật. Chỉ nhắc ngày và buổi tôi chọn cho lần này, không tìm slot hay ghi nhớ lại.",
                        lambda a, p, t: window_answer(a, "chu nhat", "sang") and has_key(p, "preferred_service_window", saves[0][3]))
        await self.turn("current_cost_override", owner, vehicle,
                        "Lần này tôi chỉ muốn xem tổng tiền. Chỉ nhắc định dạng cho lần này, không tra giá hay ghi nhớ lại.",
                        lambda a, p, t: "tong" in normalized(a) and has_key(p, "cost_display_preference", {"format": "itemized"}))
        await self.turn("one_time_no_consent", owner, vehicle,
                        "Tôi thích sáng thứ Hai cho lần này. Chỉ nhắc lựa chọn này, không tra slot.",
                        lambda a, p, t: has_key(p, "preferred_service_window", saves[0][3]) and not t and not claims_memory_save(a))
        await self.turn("negated_consent", owner, vehicle,
                        "Đừng ghi nhớ sở thích mới. Tôi chỉ thích sáng thứ Hai cho lần này, không tra slot.",
                        lambda a, p, t: has_key(p, "preferred_service_window", saves[0][3]) and not t and not claims_memory_save(a))
        if self.focus:
            self.status = "completed"
            self.flush()
            return
        await self.turn("forget_window", owner, vehicle, "Hãy quên sở thích ngày giờ bảo dưỡng của tôi.",
                        lambda a, p, t: not has_key(p, "preferred_service_window") and any(r.get("status") == "ok" and r.get("key") == "preferred_service_window" for r in t))
        await self.turn("after_forget_new_thread", owner, vehicle,
                        "Bạn còn ghi nhớ sở thích ngày và buổi bảo dưỡng của tôi không? Không tra slot.",
                        lambda a, p, t: not has_key(p, "preferred_service_window") and not window_answer(a))
        PreferenceService(self.db, self.settings).set_enabled(owner.user_id, False)
        await self.turn("disabled_save", owner, vehicle, "Hãy nhớ tôi thích chiều thứ Bảy.",
                        lambda a, p, t: not p and "chua" in normalized(a))
        await self.turn("disabled_recall", owner, vehicle,
                        "Bạn có thông tin ghi nhớ nào về định dạng chi phí của tôi? Không tra giá.",
                        lambda a, p, t: not p and unavailable_answer(a))
        PreferenceService(self.db, self.settings).set_enabled(owner.user_id, True)
        await self.turn("reenabled_recall", owner, vehicle,
                        "Theo thông tin đã ghi nhớ, định dạng chi phí tôi thích là gì? Không tra giá.",
                        lambda a, p, t: itemized_answer(a))
        await self.turn("other_owner_isolation", other, other_vehicle,
                        "Bạn biết tôi thích định dạng chi phí nào hoặc ưu tiên xưởng UUID nào không? Không tra giá.",
                        lambda a, p, t: not p and workshop_id not in a and unavailable_answer(a))

        # Seed a vehicle preference through the same consent/provenance service.
        conversation = new_conversation(self.db, owner, vehicle)
        source = add_message(self.db, conversation.id, "Hãy nhớ riêng xe này tôi thích chiều thứ Bảy.")
        PreferenceService(self.db, self.settings).remember(owner.user_id, vehicle.id, conversation.id, source.id,
                                                         "preferred_service_window", saves[0][3], scope="vehicle")
        await self.turn("other_vehicle_scope", owner, second_vehicle,
                        "Xe đang chọn có ghi nhớ ngày và buổi bảo dưỡng ưu tiên chưa? Không tra slot.",
                        lambda a, p, t: not has_key(p, "preferred_service_window") and not window_answer(a))
        cost = self.db.exec(select(AgentUserMemory).where(AgentUserMemory.memory_key == "cost_display_preference")).first()
        cost.expires_at = datetime.now(UTC) - timedelta(days=1)
        self.db.add(cost)
        self.db.commit()
        await self.turn("expired_cost", owner, vehicle,
                        "Theo thông tin đang ghi nhớ, tôi thích định dạng chi phí nào? Không tra giá.",
                        lambda a, p, t: not has_key(p, "cost_display_preference") and unavailable_answer(a))

        # Commit history first; drop checkpoint entirely and reconstruct summary
        # plus recent messages through the production SQL history service.
        for length in (50, 100):
            conversation = new_conversation(self.db, owner, vehicle)
            original = []
            for n in range(length):
                question = ("Tôi muốn kiểm tra pin trước chuyến đi Đà Nẵng." if n == 0 else
                            "Giải thích thông tin tài liệu về cách chăm sóc xe điện. " * 6)
                answer = "Nội dung trao đổi tham khảo; dữ liệu xe thực tế cần kiểm tra bằng công cụ. " * 6
                user_row = add_message(self.db, conversation.id, question)
                ai_row = add_message(self.db, conversation.id, answer, MessageRole.ASSISTANT)
                original.extend([HumanMessage(content=question, id=str(user_row.id)), AIMessage(content=answer, id=str(ai_row.id))])
            question = "Mục tiêu tôi nói ngay lúc bắt đầu cuộc trò chuyện là gì? Chỉ nhắc mục tiêu, không tra dữ liệu xe."
            def goal(a, p, t):
                text = normalized(a)
                return "pin" in text and "da nang" in text
            service = SummaryService(self.engine, self.settings)
            updated = service.update(conversation.id, force=True)
            service.mark_compacted(conversation.id, updated["version"])
            history, summary = SummaryService(self.engine, self.settings).history(conversation.id)
            # Capture recovery input before the baseline answer is committed;
            # bounded recall must not get that answer as an accidental hint.
            await self.turn(f"long_{length}_baseline", owner, vehicle, question, goal,
                            conversation=conversation, history=original, baseline=True)
            await self.turn(f"long_{length}_bounded_recovery", owner, vehicle, question, goal,
                            conversation=conversation, history=history, summary=summary)
            baseline_call = next(c for c in self.ledger.calls if c["case"] == f"long_{length}_baseline")
            bounded_call = next(c for c in self.ledger.calls if c["case"] == f"long_{length}_bounded_recovery")
            a, b = baseline_call["input_tokens"], bounded_call["input_tokens"]
            self.long_context.append({"turns": length, "baseline_input_tokens": a, "bounded_input_tokens": b,
                                      "token_reduction_percent": round((1-b/a)*100, 2) if a and b else None,
                                      "summary_version": updated["version"], "checkpoint": "discarded; reloaded committed SQL summary/history"})
            self.flush()
        self.status = "completed"
        self.flush()


async def main(args):
    if not 0 < args.budget <= 0.10:
        raise ValueError("This evaluation is authorized for at most $0.10")
    llm = get_agent_llm()
    if llm.model_name != "mistralai/mistral-small-2603":
        raise ValueError("Budget pricing is only validated for the configured Mistral model")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(get_settings().openrouter_base_url.rstrip("/") + f"/models/{llm.model_name}/endpoints")
        response.raise_for_status()
        endpoint = next(row for row in response.json()["data"]["endpoints"] if row.get("tag") == "mistral/us")
    pricing = endpoint["pricing"]
    input_rate, output_rate = float(pricing["prompt"]), float(pricing["completion"])
    if input_rate > .165/1e6 or output_rate > .66/1e6:
        raise ValueError("Endpoint price exceeds the approved estimate")
    if not 0 <= args.prior_cost < args.budget:
        raise ValueError("Prior cost must leave a positive remaining budget")
    ledger = BudgetLedger(args.budget - args.prior_cost, input_rate, output_rate)
    llm = BudgetedChatOpenAI(
        model=llm.model_name, api_key=llm.openai_api_key, base_url=llm.openai_api_base,
        max_tokens=384, temperature=0.2, timeout=30, max_retries=0, streaming=False,
        extra_body={"provider": {"only": ["mistral/us"], "allow_fallbacks": False}},
    )
    llm._ledger = ledger
    sessions = make_session()
    db = next(sessions)
    db.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    evaluation = Evaluation(db, db.get_bind(), llm, ledger, args.output, args.prior_cost, args.focus)
    # Catch schema/construction errors before sending a paid request.
    assert [convert_to_openai_tool(t) for t in evaluation.tools] == [convert_to_openai_tool(t) for t in CUSTOMER_AGENT_TOOLS]
    try:
        await evaluation.run()
    except BudgetExceeded:
        if evaluation.status == "running":
            evaluation.status = "stopped_budget"
        evaluation.flush()
    finally:
        sessions.close()
    print(json.dumps({"status": evaluation.status, "budget_accounted_usd": ledger.spent, "calls": len(ledger.calls)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, default=.10)
    parser.add_argument("--prior-cost", type=float, default=0, help="Reserve costs already spent from the same authorized budget")
    parser.add_argument("--focus", action="store_true", help="Only six window/override/consent cases; other preferences seeded through service")
    parser.add_argument("--output", type=Path, required=True)
    with asyncio.Runner(loop_factory=selector_loop_factory) as runner:
        runner.run(main(parser.parse_args()))
