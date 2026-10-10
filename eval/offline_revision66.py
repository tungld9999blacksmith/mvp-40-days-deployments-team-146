"""Replay cached evidence and model recordings; network and new fees prohibited."""
from __future__ import annotations

import asyncio
import json
import socket
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import agent_judge_audit65 as common
import offline_network_guard66 as network
from offline_evaluator66 import diagnose
from src.agents.tools.RAG.query.citation_builder import CitationBuilder
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.schemas import (
    QueryAnalysis,
    RetrievalCandidate,
    UserVehicleContext,
)
from src.infrastructure.llm.base import LLMResponse

OUTPUT = ROOT / "eval/results/agent_offline_revision_20261009_66"
PRIOR = ROOT / "eval/results/agent_judge_resume_20261009_64"


def preservation():
    history = common.verify(common.read(OUTPUT / "protected_previous_files.json"))
    prior = common.read(OUTPUT / "prior_source_manifest.json")
    changed = {name.replace("\\", "/") for name in common.verify(prior)["changed"]}
    planned = common.read(OUTPUT / "config_before.json")
    if not history["unchanged"] or changed != set(planned["allowed_source_changes"]):
        raise RuntimeError("Unexpected source or preserved-result changes")
    if common.digest(ROOT / ".env") != planned["env_sha256"]:
        raise RuntimeError("Production environment changed")
    before = OUTPUT / "before_generator.py"
    original_name = "backend/src/agents/tools/RAG/query/generator.py"
    original_hash = next(sha for name, sha in prior.items() if name.replace("\\", "/") == original_name)
    if common.digest(before) != original_hash:
        raise RuntimeError("Original generator snapshot changed")
    return {"history": history, "intentional_runtime_changes": sorted(changed),
            "unchanged_original_source_files": len(prior) - len(changed),
            "original_generator_preserved": True, "env_unchanged": True}


class RecordedProvider:
    provider_name = "openrouter"

    def __init__(self, recordings):
        self.recordings = recordings
        self.calls = 0

    async def chat(self, **kwargs):
        if self.calls >= len(self.recordings):
            raise AssertionError("No recorded generation available; live call prohibited")
        item = self.recordings[self.calls]
        self.calls += 1
        return LLMResponse(text=item["raw_text"], model="offline-recording-fixture")


def recorded_inputs(rag_entry):
    """Use the actual packaged evidence, after neighbor expansion and intent override."""
    metadata = rag_entry["response"]["metadata"]
    evidence = metadata["evidence_chunks"]
    candidates = [RetrievalCandidate.model_validate(chunk) for chunk in evidence]
    context, citations = CitationBuilder().build(candidates)
    analysis = QueryAnalysis.model_validate(metadata["query_analysis"])
    if analysis.original_query != rag_entry["tool_input"]["query"]:
        raise RuntimeError("Recorded query disagrees with tool input")
    vehicle_data = rag_entry["tool_input"].get("vehicle_context")
    vehicle = UserVehicleContext.model_validate(vehicle_data) if vehicle_data else None
    return analysis, context, citations, vehicle


async def run():
    before = preservation()
    samples = {s["sample_id"]: s for s in common.read(PRIOR / "all_selected_samples.json")}
    index = {s["sample_id"]: s for s in common.read(PRIOR / "judge_private_index.json")}
    judgments = {s["sample_id"]: s for s in common.read(PRIOR / "combined_assessments.json")}
    cache, diagnostics, replays = {}, [], []
    connect_before, connect_ex_before = socket.socket.connect, socket.socket.connect_ex
    socket.socket.connect, socket.socket.connect_ex = network.connect, network.connect_ex
    try:
        for sid, sample in samples.items():
            origin = index[sid]
            producer = ROOT / origin["producer"]
            if producer not in cache:
                cache[producer] = {row["case_id"]: row for row in (
                    json.loads(line) for line in (producer / "case_results.jsonl").read_text(encoding="utf-8").splitlines())}
            row = cache[producer][origin["case_id"]]
            if common.content_hash(row) != origin["original_row_sha256"] or sample["answer"] != row["trace"]["answer"]:
                raise RuntimeError("Original case or answer changed")
            diagnostics.append(diagnose(sample, row, judgments[sid]["automated_status"]) | {"origin": origin})
            if not origin["case_id"].startswith("NEW-R"):
                continue
            rag_entry = row["live"]["rag"][0]
            analysis, context, citations, vehicle = recorded_inputs(rag_entry)
            provider = RecordedProvider(row["live"]["generation"])
            result = await GroundedAnswerGenerator(provider).generate(analysis, context, citations, vehicle)
            if result.metadata.get("mode") == "offline_summary":
                raise RuntimeError("Recorded generation replay failed")
            replays.append({"sample_id": sid, "origin": origin, "original_answer": sample["answer"],
                            "new_offline_response": result.model_dump(), "recorded_provider_calls": provider.calls,
                            "new_external_provider_calls": 0,
                            "scope": "Cached evidence + recorded old generation, not fresh model quality or retrieval evaluation"})
    finally:
        socket.socket.connect, socket.socket.connect_ex = connect_before, connect_ex_before
    if network.BLOCKED_ATTEMPTS:
        raise RuntimeError("Offline replay attempted external connections")
    observed = [r for r in replays if r["origin"]["case_id"] == "NEW-R02"]
    if len(observed) != 2 or not all(r["new_offline_response"]["metadata"].get("documented_step_count") == 3 for r in observed):
        raise RuntimeError("Both observed procedure omissions must be repaired in offline replay")
    common.write(OUTPUT / "saved_answer_diagnostics.json", diagnostics)
    common.write(OUTPUT / "rag_recording_replays.json", replays)
    prior_cost = common.read(OUTPUT / "prior_cost.json")
    common.write(OUTPUT / "all_attempts_cost.json", {
        "prior55_through64": prior_cost, "new66_llm_cost_usd": 0,
        "new66_embedding_calls": 0, "new66_embedding_cost_usd": 0,
        "new66_qdrant_calls": 0, "new66_external_provider_calls": 0,
        "known55_through66_usd": prior_cost["all"],
        "prior_unknown_fees_remain_unknown": True,
        "scope": "Prior known receipts carried once; cached data has no new provider receipt/fee"})
    common.write(OUTPUT / "replay_completion.json", {
        "original_labels_retained": dict(Counter(j["automated_status"] for j in judgments.values())),
        "saved_answers_diagnosed": len(diagnostics), "rag_recording_replays": len(replays),
        "procedure_omissions_repaired_in_replay": len(observed),
        "new_live_outputs": 0, "new_api_cost_usd": 0,
        "network_blocked_attempts": len(network.BLOCKED_ATTEMPTS),
        "fresh_semantic_accuracy": "NOT_MEASURED", "production_acceptance": False,
        "prior_preservation": before})
    common.write(OUTPUT / "after_preservation.json", preservation())
    print(json.dumps({"diagnosed": len(diagnostics), "rag_replays": len(replays),
                      "observed_procedure_omissions_fixed": len(observed), "new_api_cost_usd": 0}))


if __name__ == "__main__":
    asyncio.run(run())
