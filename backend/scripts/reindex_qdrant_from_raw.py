"""Build a Qdrant collection directly from verified files in data/knowledge/raw.

The default target is a staging collection, so the production collection is not
modified until the staged index has passed evaluation.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "src")]

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.agents.tools.RAG.ingestion import (  # noqa: E402
    DocumentChunker,
    IngestionEngine,
    QdrantVectorStore,
    TextCleaner,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    production = os.getenv("QDRANT_COLLECTION_NAME", "ev_care_knowledge_base")
    parser.add_argument("--collection", default=f"{production}_staging")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/knowledge/raw")
    parser.add_argument(
        "--derived-dir",
        type=Path,
        default=ROOT / "knowledge/derived",
        help="Curated, source-traceable documents derived from raw files",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete and recreate only the target collection before indexing",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    engine = IngestionEngine()
    cleaner = TextCleaner()
    chunker = DocumentChunker()

    documents = engine.ingest_directory(args.raw_dir)
    if args.derived_dir.exists():
        documents.extend(engine.ingest_directory(args.derived_dir))
    chunks = []
    for document in documents:
        chunks.extend(chunker.chunk_document(cleaner.clean(document)))
    if not chunks:
        raise RuntimeError(f"No chunks produced from {args.raw_dir}")

    categories = Counter(chunk.metadata.get("category", "general") for chunk in chunks)
    models = Counter(chunk.metadata.get("model", "ALL") for chunk in chunks)
    print(f"Documents : {len(documents)}")
    print(f"Chunks    : {len(chunks)}")
    print(f"Categories: {dict(categories)}")
    print(f"Models    : {dict(models)}")

    store = QdrantVectorStore(collection_name=args.collection)
    if args.replace and store.count():
        store.clear()

    started = time.perf_counter()
    indexed = store.add_chunks(
        chunks,
        batch_size=args.batch_size,
        sleep_between_batches=0.5,
    )
    elapsed = time.perf_counter() - started
    print(f"Indexed   : {indexed}")
    print(f"Qdrant    : {store.collection_name} ({store.count()} points)")
    print(f"Elapsed   : {elapsed:.1f}s")
    return 0 if store.count() == len(chunks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
