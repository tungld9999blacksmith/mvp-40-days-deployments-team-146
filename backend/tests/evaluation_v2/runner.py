from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from pydantic import SecretStr

from src.agents.graph import build_graph, extract_text_from_content
from src.config import get_settings

from .artifacts import create_run, digest, verify_history, write_new
from .dataset import DATASET, load_dataset
from .sandbox import NOW, Sandbox
from .scoring import SCORER_VERSION, score_case, unsupported_reminder_update_claim


def load_baseline(folder: Path):
    modules = []
    for filename in ("prompts.py", "graph.py"):
        name = "src.agents._evaluation_baseline_" + uuid4().hex
        spec = importlib.util.spec_from_file_location(name, folder / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    modules[1].format_system_prompt = modules[0].format_system_prompt
    return modules[1].build_graph


def provider(model: str, args):
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY is missing")
    return ChatOpenAI(
        model=model, api_key=SecretStr(settings.openrouter_api_key), base_url=settings.openrouter_base_url,
        temperature=0.2, max_tokens=args.max_tokens, timeout=args.timeout, max_retries=0,
        extra_body={"provider": {"order": args.endpoint_order, "allow_fallbacks": True}} if args.endpoint_order else None,
    )


def calls_from_messages(messages):
    outputs = {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}
    calls = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            output = outputs.get(call["id"])
            if output is None:
                continue
            try:
                result = json.loads(output.content)
            except (ValueError, TypeError):
                result = {"text": str(output.content)}
            calls.append({"name": call["name"], "args": call["args"], "result": result, "artifact": getattr(output, "artifact", None)})
    return calls


def current_turn_calls(messages):
    start = max((i for i, message in enumerate(messages) if isinstance(message, HumanMessage)), default=-1)
    return calls_from_messages(messages[start + 1:])


def requested_calls(message):
    # An explicitly empty model request must not become a runtime-inserted read
    # in raw-model metrics. Presence, not truthiness, distinguishes the two.
    for key in ("requested_tool_calls", "rejected_tool_calls"):
        if key in message.response_metadata:
            return message.response_metadata[key]
    return message.tool_calls


async def evaluate(case, model, args, graph_builder):
    sandbox = Sandbox(case)
    case = sandbox.render(case)
    started = time.perf_counter()
    trace = {"calls": [], "answer": "", "error": None, "truncated": False}
    trace["reminder_state_before"] = sandbox.reminder_state()
    graph = None
    config = sandbox.config("eval-" + uuid4().hex)
    messages = []
    try:
        llm = provider(model, args)
        graph = graph_builder(llm=llm, tools=sandbox.tools, checkpointer=MemorySaver())
        result = await graph.ainvoke({"messages": [HumanMessage(content=case["user"])], "vehicle_context": sandbox.context, "citations": []}, config)
        messages = result["messages"]
        trace["calls"] = calls_from_messages(messages)
        trace["answer"] = next((extract_text_from_content(m.content) for m in reversed(messages) if isinstance(m, AIMessage) and not m.tool_calls), "")
        trace["messages"] = [m.model_dump(mode="json") for m in messages]
        trace["citations"] = result.get("citations", [])
        trace["confidence"] = result.get("confidence")
        trace["fallback_required"] = result.get("fallback_required")
        trace["proposal_artifacts"] = [c["artifact"] for c in trace["calls"] if isinstance(c["artifact"], dict) and c["artifact"].get("type") == "BOOKING_PROPOSAL"]
        trace["truncated"] = any(m.response_metadata.get("finish_reason") == "length" for m in messages if isinstance(m, AIMessage))
        trace["usage"] = [m.usage_metadata for m in messages if isinstance(m, AIMessage) and m.usage_metadata]
    except Exception as exc:
        trace["error"] = f"{type(exc).__name__}: {exc}"
        if graph is not None:
            try:
                checkpoint = await graph.aget_state(config)
                messages = checkpoint.values.get("messages", [])
                trace["calls"] = calls_from_messages(messages)
                trace["messages"] = [m.model_dump(mode="json") for m in messages]
            except Exception as recovery_error:
                trace["checkpoint_error"] = type(recovery_error).__name__
    finally:
        trace.update(sandbox.side_effects())
        trace["reminder_state_after"] = sandbox.reminder_state()
        trace["requested_tool_calls"] = [call for m in messages if isinstance(m, AIMessage) for call in requested_calls(m)]
        costs = [m.response_metadata.get("token_usage", {}).get("cost") for m in messages if isinstance(m, AIMessage) and (m.usage_metadata or m.response_metadata.get("token_usage"))]
        trace["provider_cost_usd"] = sum(costs) if costs and all(isinstance(c, (int, float)) for c in costs) else None
        trace["provider_models"] = sorted({m.response_metadata["model_name"] for m in messages if isinstance(m, AIMessage) and m.response_metadata.get("model_name")})
        trace["latency_seconds"] = round(time.perf_counter() - started, 3)
        metrics = score_case(case, trace, sandbox.tools)
        await sandbox.close()
    return {"case_id": case["id"], "category": case["category"], "user": case["user"], "expected": case["expected"], "trace": trace, "metrics": metrics}


async def evaluate_session(session, model, args, graph_builder):
    sandbox = Sandbox(session)
    session = sandbox.render(session)
    transcript = []
    error = None
    try:
        graph = graph_builder(llm=provider(model, args), tools=sandbox.tools, checkpointer=MemorySaver())
        config = sandbox.config("eval-session-" + uuid4().hex)
        for index, user in enumerate(session["turns"], 1):
            reminder_before = sandbox.reminder_state()
            result = await graph.ainvoke({"messages": [HumanMessage(content=user)], "vehicle_context": sandbox.context}, config)
            message = result["messages"][-1]
            effects = sandbox.side_effects()
            from .scoring import unsupported_booking_claim
            answer = extract_text_from_content(message.content)
            calls = current_turn_calls(result["messages"])
            reminder_context = any(call["name"] in {"get_reminder_settings", "update_reminder_settings", "get_reminder_context"} for call in calls) or any(term in user.casefold() for term in ("email", "nhắc", "nhac"))
            reminder_claim = reminder_context and unsupported_reminder_update_claim(answer, calls)
            transcript.append({"turn": index, "user": user, "answer": answer, "unsupported_success_claim": unsupported_booking_claim(answer), "unsupported_reminder_update_claim": reminder_claim, "current_turn_calls": calls, "messages": [m.model_dump(mode="json") for m in result["messages"]], "reminder_state_before": reminder_before, "reminder_state_after": sandbox.reminder_state(), **effects})
            if effects["booking_count_before_confirm"]:
                break
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        await sandbox.close()
    safety_passed = not any(row["booking_count_before_confirm"] or row["unsupported_success_claim"] or row["unsupported_reminder_update_claim"] for row in transcript)
    return {"session_id": session["id"], "turns": transcript, "error": error, "write_safety_passed": safety_passed, "task_success": "NEEDS_HUMAN_REVIEW"}


def summary(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)
    latencies = [r["trace"]["latency_seconds"] for r in rows]
    return {
        "attempted": len(rows), "passed": sum(r["metrics"]["task_passed"] for r in rows),
        "errors": sum(bool(r["trace"]["error"]) for r in rows),
        "safety_violations": sum(len(r["metrics"]["safety_violations"]) for r in rows),
        "categories": {key: {"passed": sum(r["metrics"]["task_passed"] for r in values), "total": len(values)} for key, values in groups.items()},
        "average_latency_seconds": statistics.fmean(latencies) if latencies else None,
        "p95_latency_seconds": sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * .95))] if latencies else None,
        "semantic_correctness": "NEEDS_HUMAN_REVIEW", "ttft": "NOT_MEASURED",
        "provider_cost_usd": sum(r["trace"]["provider_cost_usd"] for r in rows) if rows and all(r["trace"].get("provider_cost_usd") is not None for r in rows) else None,
    }


async def run(args):
    dataset = load_dataset(args.dataset)
    cases = dataset["cases"]
    if args.category:
        cases = [c for c in cases if c["category"] in args.category]
    if args.case:
        requested = set(args.case)
        cases = [c for c in cases if c["id"] in requested]
        if requested - {c["id"] for c in cases}:
            raise ValueError("Unknown case ID")
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        raise ValueError("No cases selected")
    models = args.model or [get_settings().openrouter_model_for_stage("agent")]
    configuration = {"models": models, "endpoint_order": args.endpoint_order, "repeats": args.repeats, "max_tokens": args.max_tokens, "temperature": 0.2, "timeout": args.timeout, "clock": NOW.isoformat(), "dataset_sha256": digest(args.dataset), "selected_ids": [c["id"] for c in cases], "rag_mode": "fixture_orchestration_only", "business_services": "real services on isolated SQLite/FakeAsyncRedis", "baseline_runtime": str(args.baseline_runtime) if args.baseline_runtime else None, "baseline_source_hashes": {name: digest(args.baseline_runtime / name) for name in ("graph.py", "prompts.py", "state.py")} if args.baseline_runtime else None}
    configuration["scorer_version"] = SCORER_VERSION
    directory, manifest = create_run("agent_v2", configuration, args.run_name)
    print(f"Run: {directory}", flush=True)
    snapshot = Sandbox({})
    try:
        write_new(directory / "schema_snapshot.json", {t.name: t.tool_call_schema.model_json_schema() for t in snapshot.tools})
    finally:
        await snapshot.close()
    builder = load_baseline(args.baseline_runtime) if args.baseline_runtime else build_graph
    summaries = []
    any_failure = False
    provider_stops = []
    credential_blocked = False
    with (directory / "case_results.jsonl").open("x", encoding="utf-8") as stream, (directory / "human_review.csv").open("x", encoding="utf-8", newline="") as review:
        writer = csv.writer(review)
        writer.writerow(["model_blind_id", "repeat", "case_id", "correctness", "citation_support", "task_success", "reviewer", "notes"])
        for model_index, model in enumerate(models, 1):
            for repeat in range(1, args.repeats + 1):
                rows = []
                provider_stop = None
                for index, case in enumerate(cases, 1):
                    row = await evaluate(case, model, args, builder)
                    row.update({"model": model, "repeat": repeat})
                    stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                    stream.flush()
                    writer.writerow([f"model_{model_index}", repeat, case["id"], "", "", "", "", ""])
                    review.flush()
                    rows.append(row)
                    print(f"[{model} repeat={repeat} {index}/{len(cases)}] {case['id']} {'PASS' if row['metrics']['task_passed'] else 'FAIL'}", flush=True)
                    provider_error = row["trace"]["error"] or ""
                    permanent_error = any(marker in provider_error for marker in ("AuthenticationError", "401", "402", "404"))
                    consecutive_errors = len(rows) >= 3 and all(r["trace"]["error"] for r in rows[-3:])
                    if provider_error and (index == 1 or permanent_error or consecutive_errors):
                        # Preflight failure is explicit; do not burn an entire run on
                        # the same rejected credential or unavailable endpoint.
                        provider_stop = {"model": model, "repeat": repeat, "case_id": case["id"], "error": provider_error}
                        provider_stops.append(provider_stop)
                        credential_blocked = any(marker in provider_error for marker in ("AuthenticationError", "401", "402"))
                        break
                    if args.delay:
                        await asyncio.sleep(args.delay)
                values = summary(rows)
                sessions = []
                if args.sessions and values["errors"] == 0:
                    for session in dataset["sessions"]:
                        session_result = await evaluate_session(session, model, args, builder)
                        sessions.append(session_result)
                        if session_result["error"]:
                            break  # Do not consume all sessions on a failing provider/runtime.
                values.update({"model": model, "repeat": repeat, "sessions": sessions, "selected": len(cases), "complete": len(rows) == len(cases)})
                if args.sessions:
                    values.update({"sessions_selected": len(dataset["sessions"]), "sessions_attempted": len(sessions)})
                    if sessions and sessions[-1]["error"]:
                        values["sessions_skipped_reason"] = "PROVIDER_OR_RUNTIME_ERROR_IN_SESSION"
                        values["remaining_repeats_skipped"] = args.repeats - repeat
                if args.sessions and values["errors"]:
                    values["sessions_skipped_reason"] = "PROVIDER_OR_RUNTIME_ERRORS_IN_CASES"
                if provider_stop:
                    values["remaining_repeats_skipped"] = args.repeats - repeat
                    values["provider_stop"] = provider_stop
                summaries.append(values)
                any_failure |= not values["complete"] or values["passed"] != len(cases) or any(s["error"] or not s["write_safety_passed"] for s in sessions)
                if provider_stop or (sessions and sessions[-1]["error"]):
                    break
            if credential_blocked:
                break
    write_new(directory / "comparison.json", summaries)
    write_new(directory / "review_model_key.json", {f"model_{i}": model for i, model in enumerate(models, 1)})
    if provider_stops:
        write_new(directory / "provider_stops.json", provider_stops)
    verify_history(directory, manifest)
    report = ["# Agent evaluation v2", "", "Status: DEVELOPMENT ONLY — not production acceptance.", "", "Semantic correctness, session task success, PostgreSQL/restart and UI confirmation require separate evidence/review.", "", "| Model | Repeat | PASS | Attempted / Selected | Errors | Safety violations |", "|---|---:|---:|---:|---:|---:|"]
    report.extend(f"| {r['model']} | {r['repeat']} | {r['passed']} | {r['attempted']}/{r['selected']} | {r['errors']} | {r['safety_violations']} |" for r in summaries)
    if provider_stops:
        report.extend(["", "Provider failure stopped remaining repeats for that model; authentication/credit failures also stopped remaining models. No skipped case or session is counted as passed. See provider_stops.json and comparison.json."])
    with (directory / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(report) + "\n")
    print(f"Report: {directory / 'report.md'}", flush=True)
    return 2 if any_failure else 0


def main():
    parser = argparse.ArgumentParser(description="Current production graph evaluation; immutable run artifacts")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--model", action="append")
    parser.add_argument("--category", action="append")
    parser.add_argument("--case", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=1536)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--delay", type=float, default=2)
    parser.add_argument("--sessions", action="store_true")
    parser.add_argument("--run-name")
    parser.add_argument("--baseline-runtime", type=Path)
    parser.add_argument("--endpoint-order", action="append", help="Optional OpenRouter endpoint order; captured in manifest")
    args = parser.parse_args()
    if args.repeats < 1 or args.max_tokens < 1 or (args.limit is not None and args.limit < 1):
        parser.error("repeats/max-tokens/limit must be positive")
    return asyncio.run(run(args))
