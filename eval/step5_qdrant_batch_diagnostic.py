"""Batch diagnostic: 10 dense queries with 3s sleep between each, detect WinError 10054 / stale pool."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from src.config import get_settings
from qdrant_client import QdrantClient

OUTPUT = (
    Path(__file__).parent
    / "results"
    / "step5_qdrant_batch_diagnostic_20261009.json"
)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

QUERY_COUNT = 10
SLEEP_BETWEEN = 3  # seconds — mirrors main runner


def run_diagnostic():
    settings = get_settings()
    if not settings.qdrant_url:
        print("ERROR: QDRANT_URL not configured", flush=True)
        sys.exit(1)

    print(
        f"Using URL: {settings.qdrant_url.split('?')[0]}",
        f"| prefer_grpc={settings.qdrant_prefer_grpc}",
        flush=True,
    )

    # Single shared client — same as original runner behaviour
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        prefer_grpc=settings.qdrant_prefer_grpc,
        timeout=60,
    )

    collection = settings.qdrant_collection_name
    # Fetch a real vector from the collection to use as query vector
    sample_records = client.scroll(collection_name=collection, limit=1, with_vectors=True)
    records = sample_records[0]
    if not records:
        result = {
            "error": "No records found in collection; cannot run diagnostic",
            "collection": collection,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print("ERROR:", result["error"], flush=True)
        client.close()
        sys.exit(1)

    # Extract the vector — may be a dict (named vectors) or a list
    raw_vector = records[0].vector
    if isinstance(raw_vector, dict):
        # Named vectors: pick the first one
        vector_name, query_vector = next(iter(raw_vector.items()))
        print(f"Named vector detected: '{vector_name}', dim={len(query_vector)}", flush=True)
    else:
        vector_name = None
        query_vector = raw_vector
        print(f"Unnamed vector, dim={len(query_vector)}", flush=True)

    results = []
    for i in range(QUERY_COUNT):
        if i > 0:
            print(f"  sleeping {SLEEP_BETWEEN}s ...", flush=True)
            time.sleep(SLEEP_BETWEEN)

        t0 = time.perf_counter()
        entry = {"index": i, "timestamp": datetime.now(timezone.utc).isoformat()}
        try:
            if vector_name is not None:
                from qdrant_client.models import NamedVector
                hits = client.query_points(
                    collection_name=collection,
                    query=query_vector,
                    using=vector_name,
                    limit=3,
                )
            else:
                hits = client.query_points(
                    collection_name=collection,
                    query=query_vector,
                    limit=3,
                )
            latency_ms = (time.perf_counter() - t0) * 1000
            entry.update(
                ok=True,
                latency_ms=round(latency_ms, 1),
                hits=len(hits.points) if hasattr(hits, "points") else len(hits),
            )
            print(f"  query {i}: OK  {latency_ms:.0f}ms", flush=True)
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            entry.update(
                ok=False,
                latency_ms=round(latency_ms, 1),
                error_type=type(exc).__name__,
                error_detail=str(exc),
            )
            print(f"  query {i}: ERROR {type(exc).__name__}: {exc}", flush=True)

        results.append(entry)

    client.close()

    first_error = next((r for r in results if not r["ok"]), None)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prefer_grpc": settings.qdrant_prefer_grpc,
        "collection": collection,
        "query_count": QUERY_COUNT,
        "sleep_between_seconds": SLEEP_BETWEEN,
        "success_count": sum(1 for r in results if r["ok"]),
        "error_count": sum(1 for r in results if not r["ok"]),
        "first_error_at_index": first_error["index"] if first_error else None,
        "first_error_detail": first_error.get("error_detail") if first_error else None,
        "results": results,
        "diagnosis": (
            "No errors detected — connection pool stable across 10 queries with 3s sleep"
            if not first_error
            else (
                "WinError 10054 / ConnectionResetError: server-side keep-alive timeout caused stale "
                "TCP connection in shared httpx connection pool. Fix: fresh client per case OR "
                "disable http keep-alive pooling."
                if "10054" in (first_error.get("error_detail") or "") or
                   "ConnectionReset" in (first_error.get("error_type") or "")
                else f"Unexpected error at index {first_error['index']}: {first_error.get('error_detail')}"
            )
        ),
    }

    OUTPUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {OUTPUT}", flush=True)
    print(
        f"Summary: {summary['success_count']}/{QUERY_COUNT} OK, "
        f"first_error_at={summary['first_error_at_index']}",
        flush=True,
    )
    return summary


if __name__ == "__main__":
    run_diagnostic()
