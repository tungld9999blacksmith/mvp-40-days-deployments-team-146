"""New artifacts only; mechanical metrics and narrow fact audits are not acceptance."""
import hashlib
import json
import re
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CASE_RUN = ROOT / "eval/results/agent_v2_1_booking_grounding_mistral_150_20261008_04"
SESSION_RUN = ROOT / "eval/results/agent_v2_1_booking_grounding_sessions_mistral_20261008_04"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(name, data):
    with (HERE / name).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


summaries = read(CASE_RUN / "comparison.json")
rows = [json.loads(line) for line in (CASE_RUN / "case_results.jsonl").read_text(encoding="utf-8").splitlines()]
assert len(rows) == 150 and len(summaries) == 3 and all(s["complete"] and not s["errors"] for s in summaries)
session_summary = read(SESSION_RUN / "comparison.json")[0]
sessions = session_summary["sessions"]
assert len(sessions) == 20 and all(len(s["turns"]) == 4 and not s["error"] for s in sessions)

audits = []
unique_receipts = {}
grounded = []
read_bindings = []
for session in sessions:
    for turn in session["turns"]:
        key = [session["session_id"], turn["turn"]]
        final = turn["messages"][-1].get("response_metadata", {})
        if final.get("booking_answer_grounded_in_tool_results"):
            grounded.append(key)
            calls = turn["current_turn_calls"]
            proposals = [c for c in calls if c["name"] == "propose_booking"]
            if proposals:
                primary = proposals[-1]["artifact"]["primary"]
                assert primary["timeSlot"][:5] in turn["answer"]
                assert primary["workshopName"] in turn["answer"]
                assert "email" not in turn["answer"].casefold()
                audits.append({"session_id": key[0], "turn": key[1], "check": "proposal card time/name and no email promise", "passed": True})
            else:
                slot_reads = [c for c in calls if c["name"] == "get_available_slots"]
                count = sum(slot["available"] is True for slot in slot_reads[-1]["result"]["slots"])
                assert f"{count} khung" in turn["answer"]
                audits.append({"session_id": key[0], "turn": key[1], "check": "available slot count", "expected_count": count, "passed": True})
        # Direct fixture user IDs are compared independently of the repair helper.
        ids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", turn["user"].casefold())
        if len(ids) == 1:
            for call in turn["current_turn_calls"]:
                if call["name"] in {"get_available_slots", "estimate_service_cost"}:
                    matches = call["args"].get("workshop_id") == ids[0]
                    audits.append({"session_id": key[0], "turn": key[1], "check": "executed read ID matches explicit fixture user ID", "passed": matches})
                    assert matches
        last_user = max(i for i, m in enumerate(turn["messages"]) if m.get("type") == "human")
        for message in turn["messages"]:
            cost = message.get("response_metadata", {}).get("token_usage", {}).get("cost")
            if message.get("type") == "ai" and message.get("id") and cost is not None:
                unique_receipts[message["id"]] = cost
        if any("workshop_id_from_explicit_user" in m.get("response_metadata", {}).get("normalized_fields", []) for m in turn["messages"][last_user + 1:]):
            read_bindings.append(key)

protected = read(HERE / "protected_previous_artifacts.json")
for name in ("completed_preflight_hashes.json", "completed_booking_hashes.json"):
    protected.update(read(HERE / name))
changed = [name for name, sha in protected.items() if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha]
assert not changed, changed
source = read(HERE / "source_revision.json")["source_hashes"]
assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha for name, sha in source.items())
for directory in (CASE_RUN, SESSION_RUN):
    manifest_sources = {name.replace("\\", "/"): sha for name, sha in read(directory / "manifest.json")["source_hashes"].items()}
    assert all(manifest_sources[name] == sha for name, sha in source.items() if name.startswith("backend/src/"))
write("preservation.json", {"previous_artifacts_checked": len(read(HERE / "protected_previous_artifacts.json")), "all_previously_closed_checked": len(protected), "changed_or_missing": changed})
write("completed_run_hashes.json", {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for directory in (CASE_RUN, SESSION_RUN) for path in directory.rglob("*") if path.is_file()})
write("targeted_fact_audit.json", {"scope": "STRUCTURED_TARGETED_CHECKS_NOT_FULL_SEMANTIC_REVIEW", "checks": audits, "independent_labels": 0})

suites = list(ET.parse(HERE / "final_regression_02.xml").getroot().iter("testsuite"))
tests = sum(int(s.attrib["tests"]) for s in suites)
skips = sum(int(s.attrib.get("skipped", 0)) for s in suites)
failures = sum(int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0)) for s in suites)
assert failures == 0
initial = read(ROOT / "eval/results/agent_v2_1_booking_grounding_preflight_mistral_20261008_04/comparison.json")[0]
case_cost = sum(row["trace"]["provider_cost_usd"] for row in rows)
result = {
    "scope": "DEVELOPMENT_NOT_ACCEPTANCE", "model": "mistralai/mistral-small-2603", "dataset_version": "2.1", "scorer_version": "2.2",
    "endpoint_order": ["mistral/us", "mistral/eu"], "actual_region": "NOT_CAPTURED",
    "booking_cases": {"selected": 150, "attempted": len(rows), "passed": sum(row["metrics"]["task_passed"] for row in rows),
        "repeats": [{key: summary[key] for key in ("repeat", "attempted", "passed", "errors", "safety_violations", "provider_cost_usd")} for summary in summaries],
        "provider_errors": sum(bool(r["trace"]["error"]) for r in rows), "safety_violations": sum(len(r["metrics"]["safety_violations"]) for r in rows),
        "average_latency_seconds": statistics.fmean(r["trace"]["latency_seconds"] for r in rows), "provider_cost_usd": case_cost,
        "runtime_rendered_answers": sum(bool(r["trace"]["messages"][-1].get("response_metadata", {}).get("booking_answer_grounded_in_tool_results")) for r in rows),
        "explicit_read_id_binding_cases": sum(any("workshop_id_from_explicit_user" in m.get("response_metadata", {}).get("normalized_fields", []) for m in r["trace"]["messages"]) for r in rows),
        "raw_argument_error_cases": sum(bool(r["metrics"]["raw_argument_errors"]) for r in rows),
        "failed_cases": [{"case_id": r["case_id"], "repeat": r["repeat"], "metrics": r["metrics"]} for r in rows if not r["metrics"]["task_passed"]]},
    "sessions": {"attempted": 20, "turns": 80, "errors": 0, "write_safety_passed": sum(s["write_safety_passed"] for s in sessions),
        "task_success": "NEEDS_HUMAN_REVIEW", "booking_grounded_turns": grounded, "explicit_read_id_binding_turns": read_bindings,
        "provider_cost_usd": sum(unique_receipts.values()), "unique_receipt_ai_message_ids": len(unique_receipts), "receipt_deduplication": "unique AI message IDs across transcript histories"},
    "initial_preflight": {k: initial[k] for k in ("attempted", "passed", "errors", "provider_cost_usd")},
    "session_preflight": {k: session_summary[k] for k in ("attempted", "passed", "errors", "provider_cost_usd")},
    "total_provider_receipt_cost_usd": case_cost + sum(unique_receipts.values()) + initial["provider_cost_usd"] + session_summary["provider_cost_usd"],
    "regression": {"passed": tests - skips, "skipped": skips, "failures": failures},
    "targeted_fact_checks": len(audits), "independent_review_labels": 0, "previous_artifacts_unchanged": len(read(HERE / "protected_previous_artifacts.json")),
    "limitations": ["Mechanical gates and narrow structured checks are not full semantic acceptance.", "Unsupported mixed-tool and multi-workshop/day comparisons keep model answers.", "No production deployment, actual browser/TTFT, locked independent holdout or staging acceptance."]
}
write("result.json", result)
print(json.dumps({"booking_cases": result["booking_cases"]["passed"], "sessions": result["sessions"]["write_safety_passed"], "structured_checks": len(audits), "regression": result["regression"], "old_artifacts_unchanged": result["previous_artifacts_unchanged"]}))
