from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from .embedding import BaseEmbeddingProvider, get_embedding_provider
from .metadata import DocumentChunk, SearchResult, canonicalize_vehicle_model

load_dotenv()

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """Quản lý lưu trữ và truy vấn Vector trong Qdrant Cloud hoặc Qdrant Local.
    Tuân thủ schema chuẩn hóa:
    - vector: Dense vector từ Embedding API (Google Gemini 3072 dims hoặc OpenAI)
    - payload:
        chunk_id: ID chunk gốc
        document_id: Mã tài liệu
        content: Nội dung văn bản
        page: Số trang (nếu có)
        source: Đường dẫn / Tên file nguồn
        model: Dòng xe (VF3, VF5, VF6, VF7, VF8, VF9, Evo200, Feliz, ALL...)
        category: Phân loại thông tin (maintenance, warranty, battery, pricing...)
        milestone_km: Mốc bảo dưỡng số km (nếu có)
        embedding_model: Tên mô hình embedding
        metadata: Toàn bộ từ điển metadata mở rộng
    """

    def __init__(
        self,
        collection_name: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
        prefer_grpc: bool = False,
    ) -> None:
        from src.config import get_settings

        cfg = get_settings()
        self.url = (
            url
            or cfg.qdrant_url
            or os.getenv("QDRANT_URL", "")
        ).strip()
        self.api_key = (
            api_key
            or cfg.qdrant_api_key
            or os.getenv("QDRANT_API_KEY", "")
        ).strip()
        self.collection_name = (
            collection_name
            or cfg.qdrant_collection_name
            or os.getenv("QDRANT_COLLECTION_NAME", "ev_care_knowledge_base")
        )
        self.embedding_provider = embedding_provider or get_embedding_provider()

        # Xác định kích thước vector theo provider
        self.vector_size = int(getattr(self.embedding_provider, "dimensions", 3072))
        if not hasattr(self.embedding_provider, "dimensions") and hasattr(self.embedding_provider, "model"):
            m = str(getattr(self.embedding_provider, "model", "")).lower()
            if "gemini" in m:
                self.vector_size = 3072
            elif "text-embedding-3-small" in m:
                self.vector_size = 1536
            elif "text-embedding-3-large" in m:
                self.vector_size = 3072

        # Kết nối tới Qdrant
        if self.url and self.api_key:
            self._client = QdrantClient(
                url=self.url,
                api_key=self.api_key,
                prefer_grpc=prefer_grpc,
            )
            logger.info(f"Kết nối Qdrant Cloud thành công: {self.url.split('?')[0]}")
        elif self.url:
            self._client = QdrantClient(url=self.url, prefer_grpc=prefer_grpc)
            logger.info(f"Kết nối Qdrant Server nội bộ tại: {self.url}")
        else:
            local_path = "./data/qdrant_local"
            os.makedirs(local_path, exist_ok=True)
            self._client = QdrantClient(path=local_path)
            logger.info(f"Chưa có QDRANT_URL. Sử dụng Qdrant Local Storage tại {local_path}")

        # Khởi tạo collection & payload indexes
        self._ensure_collection()

    @property
    def client(self) -> QdrantClient:
        return self._client

    def _ensure_collection(self) -> None:
        """Đảm bảo Collection tồn tại và đã cấu hình đúng vector size cùng payload indexes."""
        collections_res = self._client.get_collections()
        existing = [c.name for c in collections_res.collections]

        if self.collection_name not in existing:
            logger.info(
                f"Tạo Collection Qdrant '{self.collection_name}' (vector_size={self.vector_size}, distance=COSINE)..."
            )
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
            self._create_payload_indexes()

    def _create_payload_indexes(self) -> None:
        """Đánh chỉ mục cho các trường metadata quan trọng để tối ưu hóa lọc < 5ms."""
        fields_to_index = [
            ("model", rest_models.PayloadSchemaType.KEYWORD),
            ("category", rest_models.PayloadSchemaType.KEYWORD),
            ("document_id", rest_models.PayloadSchemaType.KEYWORD),
            ("milestone_km", rest_models.PayloadSchemaType.INTEGER),
        ]
        for field_name, schema_type in fields_to_index:
            try:
                self._client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            except Exception:
                pass

    def add_chunks(
        self,
        chunks: list[DocumentChunk],
        batch_size: int = 32,
        sleep_between_batches: float = 0.5,
    ) -> int:
        """Sinh vector bằng Embedding API và Upsert danh sách chunk lên Qdrant theo batch."""
        if not chunks:
            return 0

        import time

        total_upserted = 0
        embedding_model_name = getattr(self.embedding_provider, "model", self.embedding_provider.__class__.__name__)

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]

            # Kiểm tra xem các points trong batch đã tồn tại trong Qdrant chưa (Incremental Indexing)
            batch_point_ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, c.chunk_id)) for c in batch]
            try:
                existing_records = self._client.retrieve(
                    collection_name=self.collection_name,
                    ids=batch_point_ids,
                    with_payload=False,
                    with_vectors=False,
                )
                existing_ids = {str(r.id) for r in existing_records}
            except Exception:
                existing_ids = set()

            missing_chunks = [
                c for c in batch
                if str(uuid.uuid5(uuid.NAMESPACE_DNS, c.chunk_id)) not in existing_ids
            ]

            if not missing_chunks:
                logger.info(f"Batch {i // batch_size + 1}: Toàn bộ {len(batch)} chunks đã có trong Qdrant. Bỏ qua.")
                total_upserted += len(batch)
                continue

            texts = [c.content for c in missing_chunks]

            # Gọi Embedding API cho những chunk còn thiếu
            vectors = self.embedding_provider.embed_documents(texts)

            points: list[PointStruct] = []
            for chunk, vector in zip(missing_chunks, vectors):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id))
                meta = chunk.metadata or {}

                payload = {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.doc_id,
                    "content": chunk.content,
                    "page": meta.get("page"),
                    "source": meta.get("source", ""),
                    "model": meta.get("model", "ALL"),
                    "category": meta.get("category", "general"),
                    "milestone_km": meta.get("milestone_km"),
                    "embedding_model": str(embedding_model_name),
                    "metadata": meta,
                }

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    )
                )

            # Upsert vào Qdrant
            self._client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            total_upserted += len(points)
            logger.info(f"Đã upsert {len(points)} points vào Qdrant (tổng: {total_upserted}/{len(chunks)})")

            if sleep_between_batches > 0 and i + batch_size < len(chunks):
                time.sleep(sleep_between_batches)

        return total_upserted

    def search(
        self,
        query: str,
        n_results: int = 5,
        model: str | None = None,
        category: str | None = None,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Truy vấn tìm kiếm Dense Vector kết hợp bộ lọc Metadata trên Qdrant."""
        if not query.strip():
            return []
        model = canonicalize_vehicle_model(model)

        # 1. Sinh vector cho câu truy vấn bằng Embedding API
        query_vector = self.embedding_provider.embed_query(query)

        # 2. Xây dựng bộ lọc Qdrant Filter
        must_conditions = []

        # Lọc dòng xe: khớp với model của xe HOẶC tài liệu chung ALL
        if model and model != "ALL":
            must_conditions.append(
                Filter(
                    should=[
                        FieldCondition(key="model", match=MatchValue(value=model)),
                        FieldCondition(key="model", match=MatchValue(value="ALL")),
                    ]
                )
            )

        # Lọc danh mục dịch vụ
        if category and category not in ["all", "general"]:
            must_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        # 3. Thực thi tìm kiếm trên Qdrant (query_points trong qdrant-client >= 1.10)
        if hasattr(self._client, "query_points"):
            res = self._client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=n_results,
                query_filter=query_filter,
            )
            scored_points = res.points
        else:
            scored_points = getattr(self._client, "search")(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=n_results,
                query_filter=query_filter,
            )

        # 4. Chuẩn hóa về SearchResult
        results: list[SearchResult] = []
        for scored_point in scored_points:
            payload = scored_point.payload or {}
            chunk_id = payload.get("chunk_id", str(scored_point.id))
            content = payload.get("content", "")
            meta = payload.get("metadata", payload)
            score = round(float(scored_point.score), 4)

            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    content=content,
                    metadata=meta,
                    score=score,
                )
            )

        return results

    def get_all_chunks(self, batch_size: int = 100) -> list[dict[str, Any]]:
        """Lấy toàn bộ chunks từ Qdrant collection qua Scroll API (dùng để nạp vào BM25)."""
        all_chunks: list[dict[str, Any]] = []
        next_page_offset = None

        while True:
            records, next_page_offset = self._client.scroll(
                collection_name=self.collection_name,
                limit=batch_size,
                offset=next_page_offset,
                with_payload=True,
                with_vectors=False,
            )

            for record in records:
                payload = record.payload or {}
                all_chunks.append({
                    "chunk_id": payload.get("chunk_id", str(record.id)),
                    "doc_id": payload.get("document_id", ""),
                    "content": payload.get("content", ""),
                    "metadata": payload.get("metadata", payload),
                })

            if next_page_offset is None:
                break

        return all_chunks

    def count(self) -> int:
        """Đếm tổng số vector trong collection."""
        try:
            res = self._client.count(collection_name=self.collection_name, exact=True)
            return res.count
        except Exception:
            return 0

    def clear(self) -> None:
        """Xóa toàn bộ vector và tạo lại collection."""
        try:
            self._client.delete_collection(collection_name=self.collection_name)
            self._ensure_collection()
            logger.warning(f"Đã xóa và tạo mới Qdrant Collection '{self.collection_name}'")
        except Exception as e:
            logger.error(f"Lỗi khi clear Qdrant collection: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Thống kê chi tiết collection."""
        return {
            "collection_name": self.collection_name,
            "total_vectors": self.count(),
            "vector_size": self.vector_size,
            "qdrant_url": self.url or "local",
            "embedding_provider": self.embedding_provider.__class__.__name__,
        }
