"""Apply reviewed metadata corrections to the configured Qdrant collection."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

FIXES = (
    {
        "document_id": "dich_vu_bao_duong_ALL",
        "marker": "Tặng 50 điểm VPoint",
        "category": "general",
        "model": "ALL",
    },
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    args = parser.parse_args()
    kwargs = {"url": os.environ["QDRANT_URL"]}
    if os.getenv("QDRANT_API_KEY"):
        kwargs["api_key"] = os.environ["QDRANT_API_KEY"]
    client = QdrantClient(**kwargs, timeout=120)

    updated = 0
    for fix in FIXES:
        points, _ = client.scroll(
            collection_name=args.collection,
            scroll_filter={"must": [{"key": "document_id", "match": {"value": fix["document_id"]}}]},
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        matches = [
            point for point in points
            if fix["marker"].casefold() in str((point.payload or {}).get("content", "")).casefold()
        ]
        if not matches:
            raise RuntimeError(f"No point matches {fix['document_id']}/{fix['marker']!r}")
        for point in matches:
            payload = point.payload or {}
            metadata = dict(payload.get("metadata") or {})
            metadata.update(category=fix["category"], model=fix["model"])
            client.set_payload(
                collection_name=args.collection,
                points=[point.id],
                payload={"category": fix["category"], "model": fix["model"], "metadata": metadata},
                wait=True,
            )
            updated += 1
    print(f"Updated metadata for {updated} Qdrant point(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
