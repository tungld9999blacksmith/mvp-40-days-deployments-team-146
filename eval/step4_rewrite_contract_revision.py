"""New structured Rewrite revision; preserve closed historical runs unchanged."""
from __future__ import annotations

import argparse
import asyncio
import logging

import step4_rewrite as stage

PREVIOUS = stage.ROOT / "eval/results/step4_rewrite_retrieval_comparison_20261008_19"
MASTER = stage.ROOT / "eval/results/step4_rewrite_contract_revision_20261008_20"
ALLOWED_CHANGES = {
    "backend/src/agents/tools/RAG/query/rewriter.py",
    "backend/src/agents/tools/RAG/query/schemas.py",
}


class RevisionProvider(stage.CapturedProvider):
    @property
    def provider_name(self):
        # Preserve provider capabilities across the observation wrapper.
        return self.inner.provider_name


def run_name(phase, model_key):
    return f"step4_rewrite_contract_{phase}_{model_key}_20261008_20"


def configure():
    stage.MASTER = MASTER
    stage.run_name = run_name
    stage.CapturedProvider = RevisionProvider


def prepare():
    for filename in ("closed_master_hashes.json", "completed_producer_hashes.json"):
        if not stage.verify(stage.read(PREVIOUS / filename))["unchanged"]:
            raise RuntimeError("Closed evidence changed")
    if not stage.verify(stage.read(MASTER / "protected_previous_files.json"))["unchanged"]:
        raise RuntimeError("Historical results changed")
    before = stage.read(MASTER / "source_before.json")
    differences = stage.verify(before)["changed"]
    changed_paths = {str(c).replace("\\", "/") for c in differences}
    if not changed_paths <= ALLOWED_CHANGES:
        raise RuntimeError(f"Unexpected source changes: {differences}")
    source = {name: stage.digest(stage.ROOT / name) for name in before}
    for name in ("eval/step4_rewrite_contract_revision.py", "eval/step4_rewrite_contract_report.py",
                 "eval/test_step4_rewrite_contract.py"):
        source[name] = stage.digest(stage.ROOT / name)
    stage.write(MASTER / "source_revision.json", source)
    previous = stage.read(PREVIOUS / "manifest.json")
    for name in ("selected_cases.json", "rewrite_rubric.json", "live_corpus_lock.json", "components_lock.json"):
        with (MASTER / name).open("xb") as stream:
            stream.write((PREVIOUS / name).read_bytes())
    settings = stage.get_settings()
    for name, value in (("embedding_provider", settings.embedding_provider),
                        ("embedding_model", settings.embedding_gemini_model),
                        ("embedding_dimensions", settings.embedding_dimensions),
                        ("collection", settings.qdrant_collection_name)):
        if value != previous["configuration"][name]:
            raise RuntimeError(f"Retrieval config changed: {name}")
    env_hash = stage.digest(stage.ROOT / ".env")
    if env_hash != stage.read(MASTER / "env_before.json")["sha256"]:
        raise RuntimeError("Env changed during revision")
    stage.write(MASTER / "source_change_audit.json", {
        "changed_paths": sorted(changed_paths), "allowed_paths": sorted(ALLOWED_CHANGES),
        "old_source_preserved_as_hashes_and_two_file_copies": True,
        "rubric_and_dataset_unchanged": True,
    })
    stage.write(MASTER / "manifest.json", previous | {
        "scope": "step4_rewrite_structured_request_revision_development",
        "previous_master": str(PREVIOUS.relative_to(stage.ROOT)),
        "env_sha256": env_hash, "source_revision_sha256": stage.digest(MASTER / "source_revision.json"),
        "prompt_sha256": stage.content_hash(stage.SYSTEM_PROMPT),
        "configuration": previous["configuration"] | {
            "response_format": "json_schema", "require_parameters": True,
            "rewrite_payload_schema": "RewritePayload, seven required fields, additionalProperties=false",
        },
        "intentional_changes": [
            "Production Rewrite prompt distinguishes literal maintenance milestones from ODO/warranty/range",
            "OpenAI-compatible Rewrite requests seven-field strict JSON schema; OpenRouter requires supporting endpoints",
            "Observation wrapper forwards provider_name so structured request reaches the adapter",
        ],
        "baseline_comparison": "Historical plain-text request is a different revision; compare failure cases, not causal model quality",
        "production_model_change": False, "app_restarted": False, "gpt4o": "EXCLUDED_ALL_STAGES",
        "continuation_rule": "Same five-query pilot for all three; fresh full 30 only for pilot-eligible models",
    })
    print("Frozen new revision: same 30 queries/rubric/corpus; JSON schema request + literal milestone prompt", flush=True)


async def run(phase, model_key):
    configure()
    if not stage.verify(stage.read(MASTER / "source_revision.json"))["unchanged"]:
        raise RuntimeError("Frozen source changed")
    code = await stage.run(phase, model_key)
    folder = stage.ROOT / "eval/results" / run_name(phase, model_key)
    stage.write(folder / "closed_run_hashes.json", stage.hashes([folder]))
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "pilot", "full"])
    parser.add_argument("model", nargs="?", choices=list(stage.MODELS))
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.WARNING)
    if args.phase == "prepare":
        prepare()
    elif args.model:
        raise SystemExit(asyncio.run(run(args.phase, args.model)))
    else:
        parser.error("model required")
