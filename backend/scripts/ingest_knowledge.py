"""
Nạp Knowledge Base từ tài liệu gốc (data/knowledge/raw) lên Qdrant:
Ingest (PDF/HTML/MD/TXT) -> Clean -> Chunk -> Embedding (Gemini 3072 dims) -> Qdrant.

Đồng bộ tăng dần theo từng chunk:
- Chunk đã có trên Qdrant với nội dung giống hệt -> giữ nguyên, không gọi Embedding API.
- Chunk mới hoặc nội dung thay đổi -> embed và upsert lại.
- Chunk của tài liệu đã re-chunk nhưng không còn tồn tại -> xóa khỏi Qdrant.

Chạy từ root project:
    python backend/scripts/ingest_knowledge.py --dry-run   # chỉ thống kê, không ghi
    python backend/scripts/ingest_knowledge.py             # nạp tài liệu mới/thay đổi
    python backend/scripts/ingest_knowledge.py --prune     # xóa thêm tài liệu không còn trong raw/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    getattr(sys.stderr, "reconfigure")(encoding="utf-8")

CURRENT_DIR = Path(__file__).resolve().parent
ROOT = CURRENT_DIR.parent.parent  # backend/scripts/ -> backend/ -> root

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("IngestKnowledge")

from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointIdsList,
)

from src.agents.tools.RAG.ingestion import (
    DocumentChunk,
    DocumentChunker,
    GeminiEmbeddingProvider,
    IngestionEngine,
    QdrantVectorStore,
    TextCleaner,
)
from src.agents.tools.RAG.ingestion.metadata import PipelineResult

DEFAULT_SOURCE = ROOT / "data" / "knowledge" / "raw"
DEFAULT_REPORT = ROOT / "data" / "knowledge" / "processed" / "last_pipeline_run.json"


def _point_id(chunk_id: str) -> str:
    import uuid

    # Phải khớp với cách QdrantVectorStore.add_chunks sinh point id
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


def _load_existing(store: QdrantVectorStore) -> dict[str, dict[str, str]]:
    """document_id -> {chunk_id: content} của các point đang có trên Qdrant."""
    existing: dict[str, dict[str, str]] = defaultdict(dict)
    for item in store.get_all_chunks(batch_size=256):
        existing[item["doc_id"]][item["chunk_id"]] = item["content"]
    return existing


def build_chunks(source: Path) -> tuple[list[DocumentChunk], list[dict], list[str]]:
    engine = IngestionEngine()
    cleaner = TextCleaner()
    chunker = DocumentChunker()

    raw_docs = engine.ingest_directory(source)
    chunks: list[DocumentChunk] = []
    details: list[dict] = []
    errors: list[str] = []

    for raw in raw_docs:
        try:
            cleaned = cleaner.clean(raw)
            doc_chunks = chunker.chunk_document(cleaned)
        except Exception as e:
            errors.append(f"{raw.doc_id}: {e}")
            logger.error(f"Lỗi khi xử lý {raw.doc_id}: {e}")
            continue
        chunks.extend(doc_chunks)
        details.append({
            "doc_id": raw.doc_id,
            "title": raw.metadata.title,
            "file_type": raw.metadata.file_type,
            "model": raw.metadata.model,
            "category": raw.metadata.category,
            "raw_chars": len(raw.content),
            "cleaned_chars": cleaned.char_count,
            "chunks_count": len(doc_chunks),
        })

    return chunks, details, errors


def ingest(source: Path, report_path: Path, dry_run: bool, prune: bool, force: bool) -> None:
    t0 = time.time()
    print("=" * 75)
    print("  NẠP KNOWLEDGE BASE TỪ TÀI LIỆU GỐC LÊN QDRANT")
    print("=" * 75)
    print(f"  -> Nguồn: {source}")

    if not source.is_dir():
        raise SystemExit(f"Không tìm thấy thư mục nguồn: {source}")

    print("\n[1/3] Đọc, làm sạch và chunk tài liệu...")
    chunks, details, errors = build_chunks(source)
    print(f"  -> {len(details)} tài liệu, {len(chunks)} chunks")

    print("\n[2/3] Kết nối Qdrant và so sánh với dữ liệu hiện có...")
    store = QdrantVectorStore(embedding_provider=GeminiEmbeddingProvider())
    print(f"  -> Collection '{store.collection_name}' ({store.url.split('?')[0] or 'local'}) đang có {store.count():,} points")
    existing = _load_existing(store)

    new_by_doc: dict[str, list[DocumentChunk]] = defaultdict(list)
    for c in chunks:
        new_by_doc[c.doc_id].append(c)

    to_embed: list[DocumentChunk] = []
    to_delete: list[str] = []  # chunk_id
    print(f"\n  {'Tài liệu':<34}{'chunks':>7}{'giữ':>6}{'embed':>7}{'xóa':>6}")
    for doc_id in sorted(new_by_doc):
        old = existing.get(doc_id, {})
        new_ids = {c.chunk_id for c in new_by_doc[doc_id]}
        changed = [c for c in new_by_doc[doc_id] if force or old.get(c.chunk_id) != c.content]
        stale = [cid for cid in old if cid not in new_ids]
        # Chunk đổi nội dung phải xóa trước vì add_chunks bỏ qua id đã tồn tại
        to_delete.extend([c.chunk_id for c in changed if c.chunk_id in old] + stale)
        to_embed.extend(changed)
        kept = len(new_ids) - len(changed)
        status = "MỚI" if not old else ""
        print(f"  {doc_id:<34}{len(new_ids):>7}{kept:>6}{len(changed):>7}{len(stale):>6}  {status}")

    orphan_docs = sorted(set(existing) - set(new_by_doc))
    if orphan_docs:
        action = "sẽ xóa" if prune else "giữ nguyên (thêm --prune để xóa)"
        print(f"\n  Tài liệu trên Qdrant không còn trong nguồn ({action}): {', '.join(orphan_docs)}")

    print(f"\n  Tổng: embed {len(to_embed)} chunks, xóa {len(to_delete)} chunks lỗi thời")

    if dry_run:
        print("\n[DRY-RUN] Không ghi gì lên Qdrant.")
        return

    print("\n[3/3] Cập nhật Qdrant...")
    client = store.client
    if to_delete:
        client.delete(
            collection_name=store.collection_name,
            points_selector=PointIdsList(points=[_point_id(cid) for cid in to_delete]),
        )
        print(f"  -> Đã xóa {len(to_delete)} points lỗi thời")
    if prune:
        for doc_id in orphan_docs:
            client.delete(
                collection_name=store.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))])
                ),
            )
            print(f"  -> Đã xóa tài liệu {doc_id}")

    indexed = store.add_chunks(to_embed, batch_size=48, sleep_between_batches=1.2) if to_embed else 0
    duration = time.time() - t0
    total = store.count()

    result = PipelineResult(
        status="partial" if errors else "success",
        files_ingested=len(details),
        cleaned_documents=len(details),
        chunks_created=len(chunks),
        vectors_indexed=indexed,
        duration_seconds=round(duration, 2),
        details=details,
        errors=errors,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 75)
    print(f"  ĐÃ EMBED {indexed} CHUNKS -> Qdrant hiện có {total:,} points ({len(chunks)} chunks từ nguồn)")
    print(f"  -> Thời gian: {duration:.2f}s | Báo cáo: {report_path}")
    print("  -> Khởi động lại backend để BM25 nạp lại corpus từ Qdrant.")
    print("=" * 75)


def main() -> None:
    parser = argparse.ArgumentParser(description="Nạp tài liệu gốc vào Qdrant knowledge base.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Thư mục tài liệu gốc")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="File JSON báo cáo kết quả")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ thống kê thay đổi, không ghi lên Qdrant")
    parser.add_argument("--prune", action="store_true", help="Xóa tài liệu trên Qdrant không còn trong nguồn")
    parser.add_argument("--force", action="store_true", help="Embed lại toàn bộ chunks")
    args = parser.parse_args()
    ingest(args.source.resolve(), args.report.resolve(), args.dry_run, args.prune, args.force)


if __name__ == "__main__":
    main()
