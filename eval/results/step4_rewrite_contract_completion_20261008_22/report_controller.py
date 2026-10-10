"""Close new structured Rewrite pilots and eligible full development runs."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import step4_rewrite as stage
import step4_rewrite_contract_revision as revision


def main():
    revision.configure()
    cases = {c["id"]: c for c in stage.read(revision.MASTER / "selected_cases.json")}
    models = {}
    folders = []
    conditions = {}
    audits = {}
    labels = 0
    for key in stage.MODELS:
        models[key] = {}
        for phase in ("pilot", "full"):
            folder = stage.ROOT / "eval/results" / revision.run_name(phase, key)
            if not folder.exists():
                if phase == "pilot":
                    raise RuntimeError(f"Missing pilot for {key}")
                if models[key]["pilot"]["pilot_eligible"]:
                    raise RuntimeError(f"Eligible model {key} must complete full stage before closure")
                continue
            if not stage.verify(stage.read(folder / "closed_run_hashes.json"))["unchanged"]:
                raise RuntimeError("Closed producer changed")
            metrics = stage.read(folder / "metrics.json")
            models[key][phase] = metrics
            folders.append(folder)
            rows = [json.loads(line) for line in (folder / "case_results.jsonl").read_text(encoding="utf-8").splitlines()] if (folder / "case_results.jsonl").exists() else []
            expected_ids = stage.PILOT_IDS if phase == "pilot" else list(cases)
            if [r["case_id"] for r in rows] != expected_ids[:len(rows)]:
                raise RuntimeError("Case ID/order changed")
            if phase == "full" and not models[key]["pilot"]["pilot_eligible"]:
                raise RuntimeError("Full stage ran despite failed pilot gate")
            audits[f"{phase}_{key}"] = []
            for row in rows:
                for event in row["provider_events"]:
                    request = event["request"]
                    if request["response_format"]["type"] != "json_schema" or not request["extra_body"]["provider"]["require_parameters"]:
                        raise RuntimeError("Structured output parameters lost")
                    fingerprint = stage.content_hash({
                        "messages": request["messages"], "temperature": request["temperature"],
                        "max_tokens": request["max_tokens"], "response_format": request["response_format"],
                        "input_sha256": row["input_sha256"],
                    })
                    conditions.setdefault(row["case_id"], set()).add(fingerprint)
                payload = row["raw_payload"]
                raw_anchors = stage.anchor_checks(cases[row["case_id"]], SimpleNamespace(**payload)) if payload else None
                audits[f"{phase}_{key}"].append({
                    "case_id": row["case_id"], "raw_contract_pass": row["raw_contract_pass"],
                    "raw_anchor_checks": raw_anchors, "runtime_anchor_checks": row["anchor_checks"],
                    "raw_payload": payload, "runtime_analysis": row["analysis"],
                    "error": row["error"], "retrieval_status": row["retrieval_status"],
                })
                if raw_anchors is not None and raw_anchors["milestone_matches_literal_query"] != row["anchor_checks"]["milestone_matches_literal_query"]:
                    raise RuntimeError("Raw milestone was silently corrected by runtime")
            if (folder / "human_review.csv").exists():
                with (folder / "human_review.csv").open(encoding="utf-8", newline="") as stream:
                    labels += sum(any(r.get(f, "").strip() for f in ("correctness", "metadata_correctness", "reviewer", "notes")) for r in csv.DictReader(stream))
            if (folder / "corpus_before.json").exists() and stage.read(folder / "corpus_before.json") != stage.read(revision.MASTER / "live_corpus_lock.json"):
                raise RuntimeError("Corpus differs from previous revision")
            if (folder / "resolved_components.json").exists() and stage.read(folder / "resolved_components.json") != stage.read(revision.MASTER / "components_lock.json"):
                raise RuntimeError("Embedding/reranking components changed")
    if labels or any(len(v) != 1 for v in conditions.values()):
        raise RuntimeError("Human labels or common request conditions differ")
    all_metrics = [v for phases in models.values() for v in phases.values()]
    cost = sum(v["known_rewrite_cost_usd"] for v in all_metrics)
    preservation = stage.preservation()
    stage.write(revision.MASTER / "case_audit.json", audits)
    stage.write(revision.MASTER / "comparison_conditions.json", {
        "request_hashes_by_case": {k: next(iter(v)) for k, v in conditions.items()},
        "same_query_context_prompt_schema_temperature_budget": True,
        "same_unverified_golden_and_rubric": True, "category_override": None,
        "live_corpus": stage.read(revision.MASTER / "live_corpus_lock.json"),
        "components": stage.read(revision.MASTER / "components_lock.json"),
        "vectors_hash": "NOT_MEASURED", "historical_plain_text_revision_is_not_same_condition": True,
        "differences": ["Mistral endpoint preference; other models automatic", "Sequential provider load/time; single repeat"],
    })
    stage.write(revision.MASTER / "result.json", {
        "scope": "DEVELOPMENT_STRUCTURED_REWRITE_AND_LIVE_RETRIEVAL", "models": models,
        "known_rewrite_spend_usd": cost, "missing_rewrite_receipts": sum(v["missing_rewrite_receipts"] for v in all_metrics),
        "embedding_calls": sum(v["embedding_calls"] for v in all_metrics),
        "embedding_cost_usd": None, "total_pipeline_cost_usd": None,
        "independent_labels": 0, "semantic_accuracy": "NOT_MEASURED", "production_acceptance": False,
        "production_model_change": False, "app_restarted": False, "gpt4o": "EXCLUDED_ALL_STAGES",
        "source_revision_sha256": stage.digest(revision.MASTER / "source_revision.json"),
        "report_controller_sha256": stage.digest(Path(__file__)),
    })
    fields = ["phase", "model", "selected", "attempted", "raw_contract_pass", "anchor_all_match",
              "errors", "runtime_fallback_cases", "rewrite_mean_seconds", "known_rewrite_cost_usd",
              "document_hit_at_5", "document_mrr", "scored_golden_cases", "pilot_eligible"]
    table = []
    with (revision.MASTER / "stage_comparison.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for key, phases in models.items():
            for phase, v in phases.items():
                writer.writerow({"phase": phase, "model": stage.MODELS[key],
                                 **{f: v[f] for f in fields if f in v},
                                 **{f: v["retrieval"][f] for f in ("document_hit_at_5", "document_mrr", "scored_golden_cases")}})
                table.append(f"| {phase} | {stage.MODELS[key]} | {v['attempted']}/{v['selected']} | {v['raw_contract_pass']} | {v['anchor_all_match']} | {v['errors']} | {v['known_rewrite_cost_usd']:.9f} |")
    stage.write(revision.MASTER / "shortlist_by_stage.json", {
        "Rewrite": {key: {
            "pilot_eligible": phases["pilot"]["pilot_eligible"],
            "full_technical_checks_pass": bool(phases.get("full") and phases["full"]["complete"] and not phases["full"]["errors"] and phases["full"]["raw_contract_pass"] == 30 and phases["full"]["anchor_all_match"] == 30 and not phases["full"]["runtime_fallback_cases"]),
            "semantic_review": "DEFERRED_BY_USER", "production_change": False,
        } for key, phases in models.items()},
        "Agent": "Prior Mistral/Gemma shortlist; no new calls",
        "Generation": "Existing Mistral/Gemma pilots; next stage pending Rewrite results",
        "Write": "INACTIVE", "gpt4o": "EXCLUDED_ALL_STAGES", "qwen": "RESERVE_NOT_CALLED",
    })
    report = """# Step 4 — structured Rewrite revision, 08/10/2026

Production Rewrite prompt/request updated; current application model/env unchanged and no app restart. Same 30 original queries (24 golden +6 v2.1), unchanged rubric. Five-query pilots rerun for all three models; full 30 only for eligible pilots. Original runs and verdicts preserved.

| Phase | Model | Complete queries | Raw JSON passes | Input anchor matches | Errors | Rewrite receipt USD |
| --- | --- | --- | --- | --- | --- | ---: |
""" + "\n".join(table) + f"""

Known new Rewrite spend: **{cost:.9f} USD**. Embedding costs unknown, so no certified total pipeline cost. Local FlashRank; no generation or Write calls. No GPT-4o or fourth model.

New request: seven-field JSON schema with `require_parameters=true`; metadata extraction prompt distinguishes maintenance milestone from current ODO/warranty/range. Observation wrapper forwards provider capability. Raw model output remains scored without Markdown stripping or milestone correction. Source before/after and original file copies are preserved.

Same embedding model/dimensions, hybrid retrieval, local reranker and corpus payload as previous revision. Query-specific evidence retrieved separately; no category oracle. Golden document IDs/category/anchors are draft and unreviewed. Document hits do not certify answer correctness. No independent labels, no production acceptance. Single development repeat; no holdout, robustness or TTFT claim.

Prior revision is a different prompt/request configuration, so before/after failure counts do not isolate model quality. Paired current request conditions verified in `comparison_conditions.json`; provider routing/load differ. Preservation checks in `final_preservation.json` verify history, corpus, frozen source and env.

Next: address remaining full-run failures if present; otherwise compare stage candidates and proceed to generation Mistral/Gemma under a frozen shared revision. Review remains deferred; don't change production model on this evidence alone.
"""
    with (revision.MASTER / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(report)
    with (revision.MASTER / "report_controller.py").open("x", encoding="utf-8") as stream:
        stream.write(Path(__file__).read_text(encoding="utf-8"))
    stage.write(revision.MASTER / "final_preservation.json", preservation)
    stage.write(revision.MASTER / "completed_producer_hashes.json", stage.hashes(folders))
    stage.write(revision.MASTER / "closed_master_hashes.json", stage.hashes([revision.MASTER]))
    verification = {"master": stage.verify(stage.read(revision.MASTER / "closed_master_hashes.json")),
                    "producers": stage.verify(stage.read(revision.MASTER / "completed_producer_hashes.json")),
                    "preservation": preservation}
    stage.write(stage.ROOT / "eval/results/step4_rewrite_contract_verification_20261008_20.json", verification)
    print(json.dumps({"models": models, "known_rewrite_spend_usd": cost, "preservation": preservation}, ensure_ascii=True))


if __name__ == "__main__":
    main()
