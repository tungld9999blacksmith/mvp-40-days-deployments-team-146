"""Context benchmark; --live adds 20 synthetic recall checks, never business writes."""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.checkpoint import selector_loop_factory
from src.agents.graph import build_graph, extract_text_from_content, get_agent_llm
from src.agents.memory_context import build_memory_context, count_text, estimate_tokens
from src.agents.prompts import format_system_prompt
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from src.config import Settings


class UsageCollector(AsyncCallbackHandler):
    """Keep provider token/cost numbers only, never prompts or credentials."""

    def __init__(self):
        self.calls = []

    async def on_llm_end(self, response, **kwargs):
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
                metadata = getattr(message, "response_metadata", None) or {}
                provider_usage = metadata.get("token_usage") or {}
                self.calls.append(
                    {
                        "input_tokens": usage.get("input_tokens", provider_usage.get("prompt_tokens")),
                        "output_tokens": usage.get("output_tokens", provider_usage.get("completion_tokens")),
                        "provider_cost_usd": provider_usage.get("cost"),
                    }
                )


def offline_benchmark():
    settings = Settings(_env_file=None, agent_memory_context_mode="on")
    prompt = format_system_prompt({})
    schema_tokens = sum(
        count_text(json.dumps({"name": t.name, "description": t.description, "args": t.args}, ensure_ascii=False)) + 24
        for t in CUSTOMER_AGENT_TOOLS
    )
    scenarios = []
    for length in (50, 100):
        messages = []
        for n in range(length):
            messages.extend(
                [
                    HumanMessage(content="Tôi muốn tra mốc bảo dưỡng và xem kết quả đã xác minh. " * 8),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"name": "get_due_maintenance", "args": {}, "id": f"call-{n}", "type": "tool_call"}
                        ],
                    ),
                    ToolMessage(
                        content=json.dumps(
                            {"status": "ok", "due_status": "DUE", "note": "Synthetic test result " * 15}
                        ),
                        tool_call_id=f"call-{n}",
                    ),
                    AIMessage(content="Mốc bảo dưỡng cần đối chiếu dữ liệu hãng; đặt lịch cần xác nhận. " * 8),
                ]
            )
        messages.append(HumanMessage(content="Tiếp tục giúp tôi, lần này chọn sáng Chủ nhật."))
        summary = {
            "user_quotes": [
                {"message_id": "synthetic-source", "kind": "user_quote", "text": "Trước đó tôi muốn chiều thứ Bảy."}
            ]
        }
        baseline = estimate_tokens([SystemMessage(content=prompt), *messages]) + schema_tokens
        times = []
        result = None
        for _ in range(25):
            started = time.perf_counter()
            result = build_memory_context(messages, prompt, settings, summary=summary, tools=CUSTOMER_AGENT_TOOLS)
            times.append((time.perf_counter() - started) * 1000)
        bounded = result.estimated_tokens + schema_tokens
        scenarios.append(
            {
                "turns": length,
                "baseline_input_tokens_estimate": baseline,
                "bounded_input_tokens_estimate": bounded,
                "token_reduction_percent": round((1 - bounded / baseline) * 100, 2),
                "builder_p50_ms": round(statistics.median(times), 2),
                "builder_p95_ms": round(sorted(times)[int(len(times) * 0.95)], 2),
                "within_budget": bounded <= settings.agent_memory_input_token_budget,
            }
        )
    return {
        "method": "cl100k estimates, complete synthetic tool turns; timings are context construction only",
        "scenarios": scenarios,
    }


async def live_benchmark(endpoint: str | None = None, *, json_output: bool = False):
    settings = Settings(_env_file=None, agent_memory_context_mode="on")
    llm = get_agent_llm()  # Respect the configured provider/model; never print credentials.
    # The graph already has one retry for empty upstream error responses. Avoid
    # SDK retries multiplying the agreed 20-case benchmark cost allowance.
    llm = llm.model_copy(update={"max_retries": 0})
    input_rate, output_rate = 0.15, 0.60
    if endpoint:
        # Pin the exact endpoint; order alone still permits routing elsewhere.
        settings_for_api = Settings()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                settings_for_api.openrouter_base_url.rstrip("/") + f"/models/{llm.model_name}/endpoints"
            )
            response.raise_for_status()
            endpoint_info = next(
                (row for row in response.json()["data"]["endpoints"] if row.get("tag") == endpoint), None
            )
        if endpoint_info is None:
            raise ValueError("Requested endpoint is not listed for the configured model")
        input_rate = float(endpoint_info["pricing"]["prompt"]) * 1_000_000
        output_rate = float(endpoint_info["pricing"]["completion"]) * 1_000_000
        if input_rate > 0.165 or output_rate > 0.66:
            raise ValueError("Endpoint prices exceed the benchmark's agreed cost envelope")
        llm = llm.model_copy(
            update={
                "extra_body": {
                    **(llm.extra_body or {}),
                    "provider": {"only": [endpoint], "allow_fallbacks": False},
                }
            }
        )
    if json_output:
        # Evaluation-only output contract; production chat remains natural text.
        llm = llm.model_copy(
            update={
                "model_kwargs": {
                    **(llm.model_kwargs or {}),
                    "response_format": {"type": "json_object"},
                }
            }
        )
    graph = build_graph(
        llm,
        [],
        MemorySaver(),
        memory_settings=settings,
        system_prompt=(
            "Bạn đang kiểm thử recall sở thích bằng dữ liệu tổng hợp. Không có tool nghiệp vụ. "
            'Chỉ trả JSON {"day":"monday..sunday","period":"morning|afternoon|evening"}. '
            "Đọc preferred_service_window từ dữ liệu nhớ. Nếu lời người dùng chọn ngày/buổi khác "
            "cho lần này thì ưu tiên lựa chọn hiện tại. Không đặt lịch hoặc khẳng định slot."
        ),
    )
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    periods = ["morning", "afternoon", "evening"]
    results = []
    for n in range(20):
        preference = {"day": days[n % 7], "period": periods[n % 3]}
        override = n >= 10
        expected = {"day": "sunday", "period": "morning"} if override else preference
        question = (
            "Lần này tôi chọn sáng Chủ nhật. Trả lựa chọn cho lần này."
            if override
            else "Bạn nhớ tôi ưu tiên ngày nào và buổi nào?"
        )
        configurable = {
            "thread_id": str(uuid4()),
            "__memory_preferences": [{"key": "preferred_service_window", "scope": "account", "value": preference}],
        }
        started = time.perf_counter()
        collector = UsageCollector()
        responded = False
        error_metadata = None
        try:
            state = await asyncio.wait_for(
                graph.ainvoke(
                    {"messages": [HumanMessage(content=question)]},
                    {"configurable": configurable, "callbacks": [collector]},
                ),
                30,
            )
            responded = True
            text = extract_text_from_content(state["messages"][-1].content).strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            answer = json.loads(text)
            passed = answer == expected
            error = None
        except Exception as exc:
            passed, error = False, type(exc).__name__
            body = getattr(exc, "body", None)
            payload = body.get("error", body) if isinstance(body, dict) else {}
            metadata = payload.get("metadata") or {}
            error_metadata = {
                "http_status": getattr(exc, "status_code", None),
                "provider_name": metadata.get("provider_name"),
                "limit_source": metadata.get("limit_source"),
            }
        results.append(
            {
                "case": n + 1,
                "type": "current_request_override" if override else "recall",
                "passed": passed,
                "error_type": error,
                "error_metadata": error_metadata,
                "responded": responded,
                "provider_calls": collector.calls,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }
        )
        print(json.dumps({"live_case": n + 1, "passed": passed, "error_type": error}), flush=True)
        if error and ("Connection" in error or "Timeout" in error or "RateLimit" in error) and not collector.calls:
            break
        if error and ("Authentication" in error or "PermissionDenied" in error):
            break  # Configuration failures are not recall-quality measurements.
    passed = sum(r["passed"] for r in results)
    evaluated = sum(r["responded"] for r in results)
    calls = [call for case in results for call in case["provider_calls"]]
    input_tokens = sum(call["input_tokens"] or 0 for call in calls)
    output_tokens = sum(call["output_tokens"] or 0 for call in calls)
    provider_costs = [
        call["provider_cost_usd"] for call in calls if isinstance(call["provider_cost_usd"], (int, float))
    ]
    durations = sorted(r["duration_ms"] for r in results if r["responded"])
    usage_complete = bool(calls) and all(
        call["input_tokens"] is not None and call["output_tokens"] is not None for call in calls
    )
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    priced_model = model == "mistralai/mistral-small-2603"
    status = "completed" if evaluated == 20 else "incomplete"
    if not evaluated and any("RateLimit" in (case["error_type"] or "") for case in results):
        status = "blocked_provider_rate_limit"
    return {
        "model": model,
        "requested_endpoint": endpoint,
        "response_format": "json_object" if json_output else "text",
        "cases": results,
        "passed": passed,
        "total": len(results),
        "evaluated": evaluated,
        "status": status,
        "accuracy_percent": passed / evaluated * 100 if evaluated else None,
        "observed_call_count": len(calls),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "usage_complete": usage_complete,
        "provider_cost_usd": sum(provider_costs) if len(provider_costs) == len(calls) and calls else None,
        "token_price_estimate_usd": round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 8)
        if usage_complete and priced_model
        else None,
        "price_basis": f"OpenRouter mistral-small-2603, endpoint={endpoint or 'default'}: ${input_rate}/M input, ${output_rate}/M output; checked 2026-10-10; excludes top-up fees/tax"
        if priced_model
        else None,
        "graph_p50_ms": statistics.median(durations) if durations else None,
        "graph_p95_ms": durations[min(len(durations) - 1, int(len(durations) * 0.95))] if durations else None,
        "scope": "20 synthetic read-only recall/override cases; no booking, email or database operations",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--endpoint", help="Pin an exact OpenRouter endpoint slug for --live")
    parser.add_argument(
        "--json-output", action="store_true", help="Request JSON response format for this evaluation only"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"run_at_utc": datetime.now(UTC).isoformat(), "offline": offline_benchmark()}
    if args.live:
        with asyncio.Runner(loop_factory=selector_loop_factory) as runner:
            report["live"] = runner.run(live_benchmark(args.endpoint, json_output=args.json_output))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps({"report": str(args.output), "live_accuracy": report.get("live", {}).get("accuracy_percent")}),
        flush=True,
    )
