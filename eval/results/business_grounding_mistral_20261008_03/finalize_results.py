"""Summarize closed runs and verify that historical artifacts remain unchanged."""
import hashlib
import json
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CASE_RUN = ROOT / "eval/results/agent_v2_1_business_mistral_90_20261008_03"
SESSION_RUN = ROOT / "eval/results/agent_v2_1_business_sessions_mistral_20261008_03"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(name, payload):
    with (HERE / name).open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


summaries = read(CASE_RUN / "comparison.json")
rows = [json.loads(line) for line in (CASE_RUN / "case_results.jsonl").read_text(encoding="utf-8").splitlines()]
assert len(summaries) == 3 and len(rows) == 90 and all(row["complete"] for row in summaries)
session_summary = read(SESSION_RUN / "comparison.json")[0]
sessions = session_summary["sessions"]
assert session_summary["errors"] == 0 and len(sessions) == 20 and all(not session["error"] and len(session["turns"]) == 4 for session in sessions)

unique = {}
grounded_turns = []
for session in sessions:
    for turn in session["turns"]:
        final = turn["messages"][-1]
        if final.get("response_metadata", {}).get("business_answer_grounded_in_tool_results"):
            grounded_turns.append([session["session_id"], turn["turn"]])
        for message in turn["messages"]:
            cost = message.get("response_metadata", {}).get("token_usage", {}).get("cost")
            if message.get("type") == "ai" and message.get("id") and cost is not None:
                unique[message["id"]] = cost

protected = read(HERE / "protected_previous_artifacts.json")
protected.update(read(HERE / "completed_preflight_hashes.json"))
protected.update(read(HERE / "completed_business_hashes.json"))
for directory in (CASE_RUN, SESSION_RUN):
    for path in directory.rglob("*"):
        if path.is_file():
            protected.setdefault(str(path.relative_to(ROOT)), hashlib.sha256(path.read_bytes()).hexdigest())
changed = [name for name, sha in protected.items() if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha]
assert not changed, changed
assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha for name, sha in read(HERE / "source_revision_final.json")["source_hashes"].items())
write("preservation.json", {"previous_artifacts_checked": len(read(HERE / "protected_previous_artifacts.json")), "all_closed_artifacts_checked": len(protected), "changed_or_missing": changed})
write("completed_run_hashes.json", {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for directory in (CASE_RUN, SESSION_RUN) for path in directory.rglob("*") if path.is_file()})

xml = ET.parse(HERE / "final_regression_04.xml").getroot()
suites = list(xml.iter("testsuite"))
tests = sum(int(suite.attrib["tests"]) for suite in suites)
skipped = sum(int(suite.attrib.get("skipped", 0)) for suite in suites)
failures = sum(int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0)) for suite in suites)
assert failures == 0

summary = {
    "scope": "DEVELOPMENT_NOT_ACCEPTANCE", "model": "mistralai/mistral-small-2603",
    "dataset_version": "2.1", "scorer_version": "2.2", "endpoint_order": ["mistral/us", "mistral/eu"], "actual_provider_region": "NOT_CAPTURED",
    "business_cases": {"selected": 90, "attempted": len(rows), "passed": sum(row["metrics"]["task_passed"] for row in rows),
        "repeats": [{key: row[key] for key in ("repeat", "selected", "attempted", "passed", "errors", "safety_violations", "provider_cost_usd", "average_latency_seconds")} for row in summaries],
        "provider_errors": sum(bool(row["trace"]["error"]) for row in rows),
        "safety_violations": sum(len(row["metrics"]["safety_violations"]) for row in rows),
        "average_latency_seconds": statistics.fmean(row["trace"]["latency_seconds"] for row in rows),
        "provider_cost_usd": sum(row["trace"]["provider_cost_usd"] for row in rows),
        "runtime_rendered_answers": sum(bool(row["trace"]["messages"][-1].get("response_metadata", {}).get("business_answer_grounded_in_tool_results")) for row in rows),
        "failures": [{"case_id": row["case_id"], "repeat": row["repeat"], "metrics": row["metrics"], "requested_tool_calls": row["trace"]["requested_tool_calls"]} for row in rows if not row["metrics"]["task_passed"]],
        "source_revision": "source_revision_after.json (before zero-cost footer fix; no code changes during 90-case batch)"},
    "sessions": {"selected": 20, "attempted": len(sessions), "turns": sum(len(s["turns"]) for s in sessions),
        "provider_or_runtime_errors": sum(bool(s["error"]) for s in sessions),
        "write_safety_passed": sum(s["write_safety_passed"] for s in sessions),
        "business_grounded_turns": grounded_turns, "task_success": "NEEDS_HUMAN_REVIEW",
        "provider_cost_usd": sum(unique.values()), "cost_deduplication": "unique AI message IDs across transcript histories", "receipt_message_count": len(unique),
        "preflight": {key: session_summary[key] for key in ("selected", "attempted", "passed", "errors", "provider_cost_usd")},
        "source_revision": "source_revision_final.json"},
    "regression": {"passed": tests - skipped - failures, "skipped": skipped, "failures": failures, "xml": "final_regression_04.xml"},
    "independent_review_labels": 0, "staging": read(HERE / "environment_check.json"),
    "old_artifacts_unchanged": len(read(HERE / "protected_previous_artifacts.json")),
    "limitations": ["Mechanical gates do not measure full semantic correctness.", "Pure current-turn maintenance/cost reads use deterministic rendering; mixed-tool answers still need semantic review.", "Runtime-rendered answer count does not equal raw model error count.", "90 cases precede the small zero-cost source-label fix; final revision has regression and 20 fresh sessions with cost preflight.", "No live UI/TTFT, production deployment, independent holdout or source-owner acceptance."]
}
initial = read(ROOT / "eval/results/agent_v2_1_business_preflight_mistral_20261008_03/comparison.json")[0]
summary["initial_preflight"] = {key: initial[key] for key in ("selected", "attempted", "passed", "errors", "provider_cost_usd")}
summary["total_provider_receipt_cost_usd"] = sum((summary["business_cases"]["provider_cost_usd"], summary["sessions"]["provider_cost_usd"], session_summary["provider_cost_usd"], initial["provider_cost_usd"]))
write("result.json", summary)
print(json.dumps({"business_passed": summary["business_cases"]["passed"], "business_attempted": len(rows), "sessions": len(sessions), "regression": summary["regression"], "old_artifacts_unchanged": summary["old_artifacts_unchanged"]}))
