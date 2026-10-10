# Fix applied: Option A (fresh QdrantClient per case) + Option B (exponential backoff retry on WinError 10054 / ConnectionResetError)
"""Prospective frozen 30-case evaluation; one configuration/repeat per process."""
import argparse
import asyncio
import json
import logging
import re
import time
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import agent_content_followup as baseline

common, live = baseline.common, baseline.previous
ROOT = baseline.ROOT
MASTER = ROOT / "eval/results/step5_frozen_transport_20261009_57"
DATASET = ROOT / "eval/test_cases/agent_frozen_candidate_30_20261009.json"
PRIOR = ROOT / "eval/results/automatic_review_aggregate_20261009_54"
PIPELINE = ROOT / "eval/results/agent_content_followup_isolated_20261009_49"
PILOT_IDS = ["NEW-R02", "NEW-B04", "NEW-N02"]
ABORTED = ROOT / "eval/results/step5_frozen_20261009_55"

ORDER = [(1, "base"), (1, "agent_gemma"), (2, "agent_gemma"), (2, "base"), (3, "base"), (3, "agent_gemma")]


def preservation():
    m = common.read(MASTER / "manifest.json")
    checks = {k: common.verify(common.read(MASTER / name)) for k, name in (
        ("history", "protected_previous_files.json"), ("corpus", "protected_corpus.json"), ("source", "source_revision.json"))}
    checks.update(env_unchanged=common.digest(ROOT / ".env") == m["env_sha256"],
        dataset_unchanged=common.digest(DATASET) == m["dataset_sha256"],
        rubric_unchanged=common.digest(MASTER / "rubric.json") == m["rubric_sha256"])
    if not all(v["unchanged"] if isinstance(v, dict) else v for v in checks.values()):
        raise RuntimeError("Frozen conditions/history changed")
    return checks


def validate_dataset(dataset, old):
    cases = dataset["cases"]
    if len(cases) != 30 or len({c["id"] for c in cases}) != 30 or len({c["user"] for c in cases}) != 30:
        raise ValueError("Expected30 unique IDs/questions")
    if Counter(c["category"] for c in cases) != {"rag":6,"guardrail":5,"booking":8,"maintenance_cost":6,"reminder":5}:
        raise ValueError("Coverage differs from frozen design")
    if {c["user"] for c in cases} & {c["user"] for c in old["cases"]}:
        raise ValueError("Exact development question reused")
    for c in cases:
        e = c["expected"]
        if set(e.get("required_tools", [])) & set(e.get("forbidden_tools", [])):
            raise ValueError("Contradictory required/forbidden tools")
        if "golden" in c:
            raise ValueError("Do not reuse unverified old golden answers")


def prepare():
    if not common.verify(common.read(ABORTED / "closed_master_hashes.json"))["unchanged"]:
        raise RuntimeError("Aborted55 evidence changed")
    validate_dataset(common.read(DATASET), common.read(common.DATASET))
    if not common.verify(common.read(PRIOR / "closed_master_hashes.json"))["unchanged"]:
        raise RuntimeError("Closed previous evidence changed")
    old_source = common.read(PRIOR / "source_revision.json")
    changed = set(common.verify(old_source)["changed"])
    acknowledged = {"backend/src/agents/booking_grounding.py", "backend/src/agents/guardrails.py"}
    if {name.replace("\\", "/") for name in changed} != acknowledged:
        raise RuntimeError("Unexpected application changes beyond inspected current checkout")
    protected = common.hashes([ROOT / "eval/results", ROOT / "eval/test_cases", ROOT / "backend/tests/test_agents", ROOT / "backend/tests/evaluation"])
    MASTER.mkdir(exist_ok=False)
    common.write(MASTER / "protected_previous_files.json", protected)
    common.write(MASTER / "protected_corpus.json", common.read(PRIOR / "protected_corpus.json"))
    source = {name:common.digest(ROOT / name) for name in old_source}
    common.write(MASTER / "application_revision_audit.json", {"prior_source_manifest":str((PRIOR / "source_revision.json").relative_to(ROOT)),
        "current_checkout_changes_before_freeze":{name:{"prior_sha256":old_source[name],"current_sha256":source[name]} for name in sorted(changed)},
        "boundary":"Preexisting application edits inspected and retained; not made by this run. Both models use current checkout, historical54 cannot be treated as same-runtime model-only comparison."})
    for name in ("eval/step5_frozen.py", "eval/step5_frozen_review.py", "eval/test_step5_frozen.py", "eval/step5_frozen_transport.py", "eval/step5_frozen_transport_review.py", "eval/test_step5_frozen_transport.py", "eval/step5_frozen_transport_retry.py", "eval/step5_frozen_transport_retry_review.py", "eval/step5_frozen_transport_retry_v2.py"):
        source[name] = common.digest(ROOT / name)
    common.write(MASTER / "source_revision.json", source)
    for name in ("live_corpus_lock.json", "components_lock.json"):
        common.write(MASTER / name, common.read(PIPELINE / name))
    common.write(MASTER / "selected_cases.json", common.read(DATASET)["cases"])
    common.write(MASTER / "rubric.json", {"status":"PROSPECTIVE_FROZEN_CANDIDATE_NOT_INDEPENDENT_ACCEPTANCE",
        "scorer":"unchanged2.2 plus declarative multi-workshop and alternative-read assertions",
        "quality":"Behavior/task/raw-argument failures remain in denominator and do not stop a valid API batch; stop on safety/provider/retrieval/missing-receipt/budget failures.",
        "semantic":"Gemini Flash Lite component judge; blind to model/repeat; original sources and actual tools/state primary, expected criteria not evidence of writes. No human labels/source truth certification.",
        "freeze":"No runtime/prompt/dataset/scorer edits across repeats, no coaching from pilot/full outputs."})
    common.write(MASTER / "manifest.json", {"date":"2026-10-09","scope":"FROZEN_NEW30_TWO_CONFIGURATIONS_THREE_REPEATS",
        "independent_holdout_certified":False,"production_acceptance":False,"dataset_sha256":common.digest(DATASET),
        "rubric_sha256":common.digest(MASTER / "rubric.json"),"env_sha256":common.digest(ROOT / ".env"),
        "models":baseline.MODELS,"rewrite_model":live.MISTRAL,"generation_model":live.MISTRAL,
        "embedding":"models/gemini-embedding-001/3072","clock":"2026-10-07T09:00:00+07:00",
        "pilot_ids":PILOT_IDS,"selected_ids":[c["id"] for c in common.read(DATASET)["cases"]],
        "order":ORDER,"full_outputs":180,"receipt_caps_usd":{"all":.75,"pipeline":.23,"judge":.50},
        "budget":"Actual receipt stop before next sequential case/request, may cross threshold within in-flight case; embedding fees unknown. Pilot included, SDKretry0, no hidden paid repair.",
        "call_caps":{"agent_per_case":6,"rag_per_case":2},"gpt4o":"EXCLUDED","write":"INACTIVE",
        "qdrant_transport_timeout_seconds":60,
        "aborted_run":"eval/results/step5_frozen_20261009_55",
        "restart":"Fresh entire batch after Qdrant read timeout; no runtime/prompt/dataset/answer coaching or selective reruns.55 costs included in shared original cap.",
        "authorization":"User explicitly accepted new30 frozen candidate comparison and proposed budget; not human-reviewed holdout."})
    common.write(MASTER / "prior_flag_audit.json", {"old_labels_changed":False,"runtime_changed":False,
        "RAG-001":"Old answer source-absence facts without public citation; format FAIL remains, no automatic PASS substitution.",
        "BOOK-25":"LOCATION_ANCHOR_REQUIRED and generic fallback; task continuation remains a potential defect. No pre-holdout optimization.",
        "BOOK-03":"Judge said missing slots/proposal; actual T3 has successful slots and old expected.forbidden_tools includes propose_booking. User did not choose exact slot; judge disagreement, not established runtime defect.",
        "source_queue":"No authority/version adjudication; uncertainty remains visible in new evaluations."})
    common.write(MASTER / "prepared_preservation.json", preservation())
    print(json.dumps({"prepared":str(MASTER),"full_selected":180,"new_exact_questions":30}),flush=True)


def spent():
    pipeline = common.read(ABORTED / "all_attempts_cost.json")["pipeline"] + sum(common.read(f)["known_total_llm_cost_usd"] for f in MASTER.glob("*/metrics.json") if f.parent.name.startswith(("pilot_", "repeat")))
    judge = sum(common.read(f)["known_cost_usd"] for f in MASTER.glob("judge*/metrics.json"))
    return {"pipeline":pipeline,"judge":judge,"all":pipeline+judge}


def assertions(case, row):
    errors = []
    calls = row["trace"]["calls"]
    checks = case.get("checks", {})
    wanted = checks.get("at_least_one_tool")
    if wanted and not any(c["name"] in wanted for c in calls):
        errors.append("No accepted read tool executed")
    if checks.get("must_read_workshops"):
        asked = case["user"]
        # IDs are rendered per isolated sandbox; select directly from user text.
        uuids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", asked)
        observed = {str(c["args"].get("workshop_id")) for c in calls if c["name"] == "get_available_slots" and c["args"].get("target_date") == checks["availability_date"]}
        if len(set(uuids)) != 2 or not set(uuids).issubset(observed):
            errors.append("Both requested workshops/date were not read")
    return errors


def fatal(row, metric):
    if row["trace"].get("error") or row["metrics"]["safety_violations"] or any(metric["missing_receipts_by_stage"].values()):
        return True
    for key in ("agent", "rewrite", "generation", "rag"):
        if any(e.get("error") for e in row["live"][key]):
            return True
        if key != "rag" and any(e.get("model") != (row["agent_model"] if key == "agent" else live.MISTRAL) for e in row["live"][key]):
            return True
    return bool(row["live"]["retrieval_errors"] or row["live"]["dense_disabled"] or row["live"]["rewrite_fallback_calls"])


# --- Transport error detection helpers ---

_TRANSPORT_ERRORS = (ConnectionResetError, ConnectionError, OSError)
_TRANSPORT_ERRNO = 10054  # WinError: connection reset by peer


def _is_transport_error(exc: BaseException) -> bool:
    """Return True for WinError 10054 / ConnectionReset-style errors."""
    if isinstance(exc, _TRANSPORT_ERRORS):
        return True
    # httpx wraps OS errors; walk the cause chain
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause and isinstance(cause, _TRANSPORT_ERRORS):
        return True
    # Check errno for OSError subclasses
    errno = getattr(exc, "errno", None) or getattr(cause, "errno", None)
    if errno == _TRANSPORT_ERRNO:
        return True
    # String-match as last resort (covers httpx RemoteProtocolError wrapping)
    msg = str(exc).lower()
    return "10054" in msg or "connection reset" in msg or "connectionreset" in msg


def _make_qdrant_client(settings):
    """Create a fresh QdrantClient from the frozen settings."""
    from qdrant_client import QdrantClient
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        prefer_grpc=settings.qdrant_prefer_grpc,
        timeout=60,
    )


class TimeoutReadOnlyStore(common.ReadOnlyStore):
    """Explicit transport deadline, same read-only collection and query contract.

    Accepts an optional pre-built ``client`` keyword argument so the caller
    can pass a fresh QdrantClient per case (Option A).  Falls back to
    constructing its own client when called without one.
    """
    def __init__(self, *args, client=None, **kwargs):
        from src.infrastructure.qdrant import dependency

        settings = common.get_settings()
        if not settings.qdrant_url:
            raise RuntimeError("Configured live Qdrant URL required")
        owns_client = client is None
        if owns_client:
            client = _make_qdrant_client(settings)
        try:
            with patch.object(dependency, "get_qdrant_service", return_value=SimpleNamespace(client=client)):
                super().__init__(*args, **kwargs)
        except Exception:
            if owns_client:
                client.close()
            raise
        # Persist the client reference for external lifecycle management.
        # self.client is a read-only property on QdrantVectorStore; the actual
        # mutable backing field is self._client (set by the base __init__).
        # We also keep a named alias _eval_client for tests that don't want to
        # reach into the private _client field.
        self._eval_client = client


async def _run_case_with_retry(identifier, cases, pipeline, providers, embedding, recorded,
                               rewriter, hybrid, args, key, repeat, phase, live_runner,
                               live_module, original_provider, settings, rows, ids,
                               max_retries=3):
    """Run a single case, retrying on transport errors with exponential backoff (Option B).

    On transport errors, a fresh QdrantClient is injected into the store (Option A).
    """
    from src.infrastructure.qdrant import dependency

    attempt = 0
    last_exc = None
    while attempt <= max_retries:
        if attempt > 0:
            backoff = min(2 ** attempt, 30)  # 2s, 4s, 8s … capped at 30s
            print(f"  [retry {attempt}/{max_retries} for {identifier}] sleeping {backoff}s after transport error …", flush=True)
            await asyncio.sleep(backoff)

            # Option A: replace the Qdrant client in the shared store with a fresh one
            old_client = getattr(pipeline._rag_pipeline._retriever._vector_store._store, "_client", None)
            new_client = _make_qdrant_client(settings)
            if old_client is not None:
                try:
                    old_client.close()
                except Exception:
                    pass

            # Swap _client directly on the store object (client is a read-only property)
            try:
                store_obj = pipeline._rag_pipeline._retriever._vector_store._store
                store_obj._client = new_client
                store_obj._eval_client = new_client  # keep alias in sync
            except Exception:
                pass  # non-fatal; outer loop's per-case swap already covers this

        try:
            observer = live_module.AgentCapture()
            for provider in providers:
                provider.events.clear()
            embedding.events.clear()
            recorded.errors.clear()
            rewriter.fallback_calls = 0
            pipeline.reset()

            def agent_provider(model, arguments, capture=observer):
                return original_provider(model, arguments).model_copy(update={"callbacks": [capture]})

            live_sandbox = live_module.Sandbox

            class LiveSandbox(live_sandbox):
                def __init__(self, case):
                    super().__init__(case, rag_pipeline=pipeline)

            with (patch.object(live_runner, "Sandbox", LiveSandbox),
                  patch.object(live_runner, "provider", agent_provider)):
                row = await live_runner.evaluate(cases[identifier], baseline.MODELS[key], args, live_runner.build_graph)

            row.update(
                agent_model=baseline.MODELS[key],
                configuration_key=key,
                repeat=repeat,
                live={
                    "agent": observer.events,
                    "rewrite": list(providers[0].events) if len(providers) > 0 else [],
                    "generation": list(providers[1].events) if len(providers) > 1 else [],
                    "embedding": list(embedding.events),
                    "rag": list(pipeline.events),
                    "retrieval_errors": list(recorded.errors),
                    "dense_disabled": hybrid._dense_disabled,
                    "rewrite_fallback_calls": rewriter.fallback_calls,
                },
            )
            return row, observer

        except Exception as exc:  # noqa: BLE001
            if _is_transport_error(exc) and attempt < max_retries:
                last_exc = exc
                attempt += 1
                continue
            raise

    # Exhausted retries — re-raise last transport exception
    raise last_exc  # type: ignore[misc]


async def run(phase, key, repeat):
    preservation()
    if phase == "full":
        expected_index = ORDER.index((repeat, key))
        for r, k in ORDER[:expected_index]:
            metrics = common.read(MASTER / f"repeat{r}_{k}/metrics.json")
            if not metrics["complete"] or metrics["preflight_error"]:
                raise RuntimeError("Earlier scheduled configuration incomplete")
        for k in baseline.MODELS:
            folder = MASTER / f"pilot_{k}"
            if not common.verify(common.read(folder / "closed_run_hashes.json"))["unchanged"]:
                raise RuntimeError("Pilot changed")
            m = common.read(folder / "metrics.json")
            if not m["complete"] or m["preflight_error"] or m["safety_violations"] or any(m["missing_receipts_by_stage"].values()):
                raise RuntimeError("Pilot API/safety qualification incomplete")
    ids = PILOT_IDS if phase == "pilot" else common.read(MASTER / "manifest.json")["selected_ids"]
    cases = {c["id"]:c for c in common.read(MASTER / "selected_cases.json")}
    folder = MASTER / (f"pilot_{key}" if phase == "pilot" else f"repeat{repeat}_{key}")
    folder.mkdir(exist_ok=False)
    common.write(folder / "manifest.json",common.read(MASTER / "manifest.json")|{"phase":phase,"repeat":repeat,"configuration":key,"selected_ids":ids})
    rows, providers, store, error = [], [], None, None
    try:
        settings = common.get_settings()
        if settings.embedding_provider != "gemini" or settings.embedding_dimensions != 3072:
            raise RuntimeError("Frozen Gemini3072 embedding required")
        embedding = common.ObservedEmbedding(common.create_embedding_engine(settings))
        store = TimeoutReadOnlyStore(embedding_provider=embedding)
        before = live.corpus_snapshot(store)
        common.write(folder / "corpus_before.json",before)
        if before != common.read(MASTER / "live_corpus_lock.json"):
            raise RuntimeError("Live corpus changed")
        recorded = common.RecordedStore(store)
        hybrid = common.HybridRetriever(vector_store=recorded)
        if not hybrid.sync_bm25_from_vector_store():
            raise RuntimeError("BM25 unavailable")
        reranker = common.RerankerService()
        components = {"reranker":type(reranker._reranker).__name__,"reranker_model":getattr(reranker._reranker,"model_name",getattr(reranker._reranker,"model",None)),"embedding":embedding.model,"dimensions":embedding.dimensions}
        if components != common.read(MASTER / "components_lock.json"):
            raise RuntimeError("Retrieval components changed")
        common.write(folder / "resolved_components.json",components)
        for _ in range(2):
            inner = common.create_llm_provider(settings.model_copy(update={"openrouter_model":live.MISTRAL,"openrouter_endpoint_order":"mistral/us,mistral/eu"}),"openrouter")
            inner._client = inner._client.with_options(max_retries=0,timeout=60)
            providers.append(live.RevisionProvider(inner,live.MISTRAL))
        rewrite,generate = providers
        rewriter = common.ObservedRewriter(rewrite)
        pipeline = live.LiveRAG(live.RAGPipeline(rewriter=rewriter,hybrid_retriever=hybrid,reranker=reranker,generator=live.GroundedAnswerGenerator(generate)))
        args = SimpleNamespace(max_tokens=2048,timeout=60,endpoint_order=["mistral/us","mistral/eu"] if key=="base" else [])
        original_provider = live.runner.provider

        with (folder / "case_results.jsonl").open("x", encoding="utf-8") as f:
            for identifier in ids:
                cost = spent()
                if cost["pipeline"] + baseline.metrics(rows,ids)["known_total_llm_cost_usd"] >= .23 or cost["all"] + baseline.metrics(rows,ids)["known_total_llm_cost_usd"] >= .75:
                    error = "Receipt budget reached; remaining cases unattempted"
                    break

                # --- Option A: fresh QdrantClient for this case ---
                # client is a read-only property; swap the backing _client field.
                new_client = _make_qdrant_client(settings)
                old_client = getattr(store, "_client", None)
                if old_client is not None and old_client is not new_client:
                    try:
                        old_client.close()
                    except Exception:
                        pass
                store._client = new_client
                store._eval_client = new_client  # keep alias in sync
                # --- end Option A setup ---

                # --- Option B: retry wrapper handles transport errors ---
                try:
                    row, observer = await _run_case_with_retry(
                        identifier, cases, pipeline, providers, embedding, recorded,
                        rewriter, hybrid, args, key, repeat, phase, live.runner,
                        live, original_provider, settings, rows, ids,
                    )
                except Exception as exc:  # noqa: BLE001
                    error = f"{type(exc).__name__}: {exc}"
                    break
                # --- end Option B ---

                row["configuration_gate"] = live.analyze(row)
                extra = assertions(cases[identifier]|{"user":row["user"]},row)
                row["configuration_gate"]["failures"].extend(extra)
                row["configuration_gate"]["technical_pass"] &= not extra
                rows.append(row)
                f.write(json.dumps(row,ensure_ascii=False,default=str)+"\n");f.flush()
                print(f"[{phase} {key} r{repeat} {len(rows)}/{len(ids)}] {identifier} {'PASS' if row['configuration_gate']['technical_pass'] else 'FAIL'}",flush=True)
                if fatal(row,baseline.metrics(rows,ids)):
                    error = "Safety/provider/retrieval/receipt stop; labels retained, no retry"
                    break
                await asyncio.sleep(3)

        after = live.corpus_snapshot(store)
        common.write(folder / "corpus_after.json",after|{"unchanged":after==before})
        if before != after:
            raise RuntimeError("Live corpus changed")
    except Exception as exc:  # noqa: BLE001 -- retain interrupted evaluations without retry/repair
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for provider in providers:
            await provider.inner._client.close()
        if store:
            # Close the most recent client held by the store (_client is the backing field)
            client_to_close = getattr(store, "_client", None)
            if client_to_close is not None:
                try:
                    client_to_close.close()
                except Exception:
                    pass
    result = baseline.metrics(rows,ids,error)
    common.write(folder / "metrics.json",result)
    common.write(folder / "preservation.json",preservation())
    common.write(folder / "closed_run_hashes.json",common.hashes([folder]))
    print(json.dumps(result),flush=True)
    return 0 if result["complete"] and not error else 2


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase",choices=("prepare","pilot","full"))
    p.add_argument("configuration",nargs="?",choices=list(baseline.MODELS))
    p.add_argument("--repeat",type=int,choices=(1,2,3),default=1)
    a=p.parse_args();logging.disable(logging.WARNING)
    if a.phase=="prepare":
        prepare()
    elif a.configuration:
        raise SystemExit(asyncio.run(run(a.phase,a.configuration,a.repeat)))
    else:
        p.error("One explicit configuration per process is required")
