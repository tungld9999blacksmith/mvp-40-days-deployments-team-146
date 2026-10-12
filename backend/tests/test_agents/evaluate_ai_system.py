"""Master evaluation runner for the EV Care AI system."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
TEST_AGENTS = BACKEND / "tests" / "test_agents"
EVALUATION = BACKEND / "tests" / "evaluation"
RAG_EVAL = EVALUATION / "rag"
AGENT_EVAL = EVALUATION / "llm_agent"
load_dotenv(ROOT / ".env")
sys.path[:0] = [str(BACKEND), str(BACKEND / "src")]

from config import get_settings  # noqa: E402


def run_name_now() -> str:
    return datetime.now().astimezone().strftime("run_%Y%m%d_%H%M%S")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def execute(name: str, command: list[str]) -> dict[str, Any]:
    print("\n" + "=" * 72)
    print(name)
    print("=" * 72)
    print("$ " + " ".join(command))
    started = time.perf_counter()
    process = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, env=os.environ.copy(), check=False,
    )
    print(process.stdout, end="")
    return {
        "name": name,
        "status": "PASS" if process.returncode == 0 else "FAIL",
        "return_code": process.returncode,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "command": command,
        "output_tail": process.stdout[-5000:],
    }


def parse_pytest(output: str, status: str) -> dict[str, Any]:
    def number(label: str) -> int:
        match = re.search(rf"(\d+)\s+{label}", output)
        return int(match.group(1)) if match else 0
    return {
        "status": status,
        "passed": number("passed"),
        "failed": number("failed"),
        "skipped": number("skipped"),
    }


def environment_snapshot() -> dict[str, Any]:
    settings = get_settings()
    return {
        "agent_model": settings.openrouter_agent_model,
        "rag_generation_model": settings.openrouter_rag_model,
        "rewrite_model": settings.openrouter_rewrite_model,
        "write_review_model": settings.openrouter_write_model,
        "qdrant_collection": settings.qdrant_collection_name,
        "openrouter_key_configured": bool(settings.openrouter_api_key),
        "gemini_key_configured": bool(settings.gemini_api_key),
        "qdrant_configured": bool(settings.qdrant_url and settings.qdrant_api_key),
    }


def status_from_file(path: Path, resolver) -> str:
    payload = read_json(path)
    return resolver(payload) if payload else "NOT RUN"


def fmt_metric(value: Any, *, percent: bool = False) -> str:
    if value is None:
        return "NOT MEASURED"
    if isinstance(value, str):
        return value
    if percent:
        return f"{float(value):.2%}"
    return str(value)


def render_system_report(payload: dict[str, Any], path: Path) -> None:
    env = payload["environment"]
    pytest = payload["automated_tests"]
    rag_smoke = payload.get("rag_smoke") or {}
    retrieval = (payload.get("retrieval") or {}).get("metrics", {})
    full = (payload.get("full_rag") or {}).get("metrics", {})
    agent = payload.get("agent") or {}
    categories = (agent.get("summary") or {}).get("categories", {})
    known = agent.get("known_issues", {})
    critical = agent.get("critical_failures", [])
    lines = [
        "# EV Care AI System Evaluation", "",
        f"Run: `{payload['run_name']}`", "",
        "## Environment", "",
        f"Agent model: `{env.get('agent_model')}`  ",
        f"RAG generation model: `{env.get('rag_generation_model')}`  ",
        f"Embedding model: `{rag_smoke.get('environment', {}).get('embedding_model', 'NOT MEASURED')}`  ",
        f"Embedding dimension: `{rag_smoke.get('environment', {}).get('embedding_dimension', 'NOT MEASURED')}`  ",
        f"Qdrant collection: `{rag_smoke.get('environment', {}).get('qdrant_collection', env.get('qdrant_collection'))}`  ",
        f"Qdrant points: `{rag_smoke.get('environment', {}).get('qdrant_points', 'NOT MEASURED')}`  ",
        f"Reranker: `{rag_smoke.get('environment', {}).get('reranker', 'NOT MEASURED')}`", "",
        "## Automated Tests", "",
        f"Status: **{pytest['status']}**  ",
        f"Passed: {pytest['passed']}  ", f"Failed: {pytest['failed']}  ", f"Skipped: {pytest['skipped']}", "",
        "## RAG Smoke", "", f"Status: **{rag_smoke.get('status', 'NOT RUN')}**", "",
        "## Retrieval", "", "| Metric | Score |", "|---|---:|",
        f"| Hit@1 | {fmt_metric(retrieval.get('hit_at_1'), percent=True)} |",
        f"| Hit@3 | {fmt_metric(retrieval.get('hit_at_3'), percent=True)} |",
        f"| Hit@5 | {fmt_metric(retrieval.get('hit_at_5'), percent=True)} |",
        f"| MRR | {fmt_metric(retrieval.get('mrr'))} |",
        f"| Avg latency | {fmt_metric(retrieval.get('average_latency_ms'))} ms |",
        f"| P95 latency | {fmt_metric(retrieval.get('p95_latency_ms'))} ms |", "",
        "## Full RAG", "", "| Metric | Score |", "|---|---:|",
        f"| Retrieval success | {fmt_metric(full.get('retrieval_success'), percent=True)} |",
        f"| Faithfulness (heuristic) | {fmt_metric(full.get('faithfulness_heuristic'), percent=True)} |",
        f"| Answer quality/correctness (heuristic) | {fmt_metric(full.get('answer_correctness_heuristic'), percent=True)} |",
        f"| Citation validity | {fmt_metric(full.get('citation_validity'), percent=True)} |",
        f"| Avg latency | {fmt_metric(full.get('average_latency_ms'))} ms |",
        f"| P95 latency | {fmt_metric(full.get('p95_latency_ms'))} ms |",
        f"| Hallucination rate (negative cases) | {fmt_metric(full.get('hallucination_rate_negative_cases'), percent=True)} |",
        f"| General hallucination rate | {fmt_metric(full.get('hallucination_rate_general'))} |", "",
        "Only measured metrics are numeric. General hallucination rate remains `NOT MEASURED` without a semantic/human judge.", "",
        "## Agent", "", "| Category | Pass | Fail | Score |", "|---|---:|---:|---:|",
    ]
    for category in ["Maintenance", "Cost", "RAG", "Workshop/Booking", "Multi-step", "Guardrail", "Error handling"]:
        item = categories.get(category, {})
        lines.append(
            f"| {category} | {item.get('pass', 0)} | {item.get('fail', 0)} | "
            f"{fmt_metric(item.get('score'), percent=True)} |"
        )
    guardrail = (agent.get("summary") or {}).get("guardrail_category", {})
    if guardrail:
        lines += [
            "", "Guardrail detail:", "",
            f"- End-to-end case pass: **{guardrail['case_pass']}/{guardrail['total']} "
            f"({guardrail['case_pass_rate']:.2%})**.",
            f"- Safety-rule compliance inside the three dedicated guardrail cases: "
            f"**{guardrail['safety_pass']}/{guardrail['total']} "
            f"({guardrail['safety_compliance_rate']:.2%})**.",
            "- `GUARD-02` was safe but incomplete: it refused fabrication and then failed to call the required tools.",
        ]
    lines += ["", "## Known Issues", ""]
    for case_id in ("BOOK-03", "RAG-02", "BOOK-04"):
        item = known.get(case_id, {})
        lines.append(f"{case_id}: **{item.get('status', 'NOT TESTABLE')}**")
    lines += ["", "## Critical Failures", ""]
    if not agent:
        lines.append("NOT MEASURED — Agent evaluation did not run.")
    elif critical:
        for item in critical:
            lines.append(f"- {item['rule']} (`{item['case_id']}`, {item['classification']})")
    else:
        lines.append("No critical failure was observed in this run.")
    lines += ["", "## Failure Analysis", ""]
    failures = agent.get("failure_analysis", [])
    if not agent:
        lines.append("NOT MEASURED — Agent evaluation did not run.")
    elif failures:
        for item in failures:
            lines.append(
                f"- `{item['case_id']}` — **{item['classification']}**; "
                f"expected `{item['expected_tools']}`, actual `{item['actual_tools']}`."
            )
    else:
        lines.append("No failed Agent case was recorded.")
    lines += ["", "## MVP Readiness", "", f"**{payload['mvp_readiness']}**", "", payload["readiness_reason"], ""]
    lines += [
        "## Recommended Actions", "",
        "### P0", "", "Resolve every critical safety failure before release.", "",
        "### P1", "", "Review failed retrieval, tool-sequence and grounded-generation cases from raw evidence.", "",
        "### P2", "", "Repeat latency/cost runs to measure variance after correctness and safety are stable.", "",
        "## Evidence Paths", "",
        f"- RAG: `{payload['paths']['rag_run']}`",
        f"- Agent: `{payload['paths']['agent_result']}`",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the complete EV Care AI system evaluation")
    parser.add_argument("--run-name", default=run_name_now())
    parser.add_argument(
        "--reuse-run", action="store_true",
        help="Run pytest, then aggregate existing RAG/Agent results for --run-name without repeating paid evaluation",
    )
    parser.add_argument(
        "--reuse-pytest", action="store_true",
        help="With --reuse-run, reuse the previous master report's pytest evidence",
    )
    parser.add_argument("--heuristic-rewriter", action="store_true")
    parser.add_argument("--full-sample-per-category", type=int, default=1)
    parser.add_argument("--agent-limit", type=int)
    parser.add_argument("--agent-inter-case-delay", type=float, default=0.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        raise SystemExit("Invalid --run-name")
    env = environment_snapshot()
    print("ENVIRONMENT CHECK")
    print(json.dumps(env, ensure_ascii=False, indent=2))
    raw_master = EVALUATION / "ai_system_evaluation.json"
    previous_master = read_json(raw_master) if args.reuse_pytest else None
    reused_pytest = (previous_master or {}).get("automated_tests")
    if args.reuse_pytest and not reused_pytest:
        raise SystemExit("--reuse-pytest requested but previous pytest evidence is unavailable")
    steps: list[dict[str, Any]] = []
    if reused_pytest:
        print("Reusing previous pytest evidence; tests were not repeated.")
    else:
        steps.append(execute("EXISTING AGENT PYTEST", [
            sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
            "backend/tests/test_agents/", "-v",
        ]))
    if not args.reuse_run:
        common = ["--run-name", args.run_name]
        rewrite = ["--heuristic-rewriter"] if args.heuristic_rewriter else []
        steps.append(execute("RAG SMOKE", [sys.executable, str(TEST_AGENTS / "evaluate_rag.py"), "--mode", "smoke", *common, *rewrite]))
        steps.append(execute("RAG RETRIEVAL", [sys.executable, str(TEST_AGENTS / "evaluate_rag.py"), "--mode", "retrieval", *common, *rewrite]))
        steps.append(execute("FULL RAG", [
            sys.executable, str(TEST_AGENTS / "evaluate_rag.py"), "--mode", "full", *common,
            "--sample-per-category", str(args.full_sample_per_category), *rewrite,
        ]))
        agent_command = [
            sys.executable, str(TEST_AGENTS / "evaluate_agent.py"),
            "--run-name", args.run_name, "--inter-case-delay", str(args.agent_inter_case_delay),
        ]
        if args.agent_limit:
            agent_command += ["--limit", str(args.agent_limit)]
        steps.append(execute("PRODUCTION AGENT + MULTI-TURN + GUARDRAIL + KNOWN ISSUES", agent_command))
    else:
        print(f"Reusing existing run: {args.run_name}")

    pytest_step = next((step for step in steps if step["name"] == "EXISTING AGENT PYTEST"), None)
    pytest_result = reused_pytest or (
        parse_pytest(pytest_step["output_tail"], pytest_step["status"])
        if pytest_step else {"status": "NOT RUN", "passed": 0, "failed": 0, "skipped": 0}
    )
    rag_run = RAG_EVAL / "results" / args.run_name
    smoke = read_json(rag_run / "smoke" / "report.json")
    retrieval = read_json(rag_run / "retrieval" / "report.json")
    full = read_json(rag_run / "full_rag" / "report.json")
    agent_path = AGENT_EVAL / "results" / args.run_name / "agent_report.json"
    agent = read_json(agent_path)
    critical = (agent or {}).get("critical_failures", [])
    core_missing = any(item is None for item in (smoke, retrieval, full, agent))
    if core_missing or pytest_result["status"] != "PASS":
        readiness = "NOT READY"
        reason = "Required full-RAG, Agent, or complete pytest evidence is missing or did not pass."
    elif critical or (smoke and smoke.get("status") != "SYSTEM WORKING"):
        readiness = "NOT READY"
        reason = "Critical safety failures or a non-working RAG smoke check were observed."
    elif agent and agent.get("summary", {}).get("failed", 0):
        readiness = "READY WITH KNOWN ISSUES"
        reason = "Core execution works, but non-critical Agent quality or regression failures remain."
    else:
        readiness = "READY"
        reason = "All executed checks passed and no critical safety failure was observed."
    payload = {
        "run_name": args.run_name, "environment": env, "steps": steps,
        "automated_tests": pytest_result, "rag_smoke": smoke,
        "retrieval": retrieval, "full_rag": full, "agent": agent,
        "mvp_readiness": readiness, "readiness_reason": reason,
        "paths": {
            "rag_run": str(rag_run.relative_to(ROOT)),
            "agent_result": str(agent_path.relative_to(ROOT)),
        },
    }
    raw_master.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = EVALUATION / "AI_SYSTEM_EVALUATION.md"
    render_system_report(payload, report_path)
    print("\n" + "=" * 72)
    print("AI SYSTEM EVALUATION SUMMARY")
    print("=" * 72)
    for step in steps:
        print(f"{step['name']}: {step['status']}")
    print(f"MVP readiness: {readiness}")
    print(f"Report: {report_path}")
    return 0 if readiness == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
