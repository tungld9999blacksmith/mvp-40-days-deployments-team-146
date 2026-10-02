from __future__ import annotations

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models
from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class QdrantService:
    """Service quản lý kết nối và thao tác với Qdrant Cloud hoặc Qdrant Local."""

    def __init__(
        self,
        url: str = settings.qdrant_url,
        api_key: str = settings.qdrant_api_key,
        prefer_grpc: bool = settings.qdrant_prefer_grpc,
    ) -> None:
        self.url = url
        self.api_key = api_key

        if self.url and self.api_key:
            # Kết nối Qdrant Cloud Cluster
            self._client = QdrantClient(
                url=self.url,
                api_key=self.api_key,
                prefer_grpc=prefer_grpc,
            )
            logger.info(f"Kết nối Qdrant Cloud thành công: {self.url.split('?')[0]}")
        elif self.url:
            # Kết nối Qdrant Server nội bộ (Docker localhost:6333)
            self._client = QdrantClient(url=self.url, prefer_grpc=prefer_grpc)
            logger.info(f"Kết nối Qdrant Local Server tại: {self.url}")
        else:
            # Fallback in-memory / local storage nếu chưa cấu hình Cloud URL
            self._client = QdrantClient(path="./data/qdrant_local")
            logger.info("Chưa có QDRANT_URL. Sử dụng Qdrant Local Storage tại ./data/qdrant_local")

    @property
    def client(self) -> QdrantClient:
        return self._client

    def ensure_collection(
        self,
        collection_name: str = settings.qdrant_collection_name,
        vector_size: int = 768,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """Đảm bảo Collection tồn tại trong Qdrant. Nếu chưa có thì tự động tạo mới."""
        collections_response = self._client.get_collections()
        existing_names = [col.name for col in collections_response.collections]

        if collection_name not in existing_names:
            logger.info(f"Đang tạo Collection mới '{collection_name}' với vector_size={vector_size}...")
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance),
            )
            # Tạo Payload Index để tối ưu tốc độ lọc Metadata
            self.create_payload_indexes(collection_name)
            return True

        return False

    def create_payload_indexes(self, collection_name: str = settings.qdrant_collection_name) -> None:
        """Đánh chỉ mục cho các trường metadata quan trọng (model, category, document_id) giúp query dưới 5ms."""
        fields_to_index = [
            ("model", rest_models.PayloadSchemaType.KEYWORD),
            ("category", rest_models.PayloadSchemaType.KEYWORD),
            ("document_id", rest_models.PayloadSchemaType.KEYWORD),
            ("milestone_km", rest_models.PayloadSchemaType.INTEGER),
        ]
        for field_name, schema_type in fields_to_index:
            try:
                self._client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            except Exception:
                pass

    def upsert_points(
        self,
        collection_name: str,
        points: list[PointStruct],
        batch_size: int = 64,
    ) -> int:
        """Nạp danh sách Point (vector + payload) lên Qdrant theo batch."""
        if not points:
            return 0

        total_upserted = 0
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self._client.upsert(
                collection_name=collection_name,
                points=batch,
            )
            total_upserted += len(batch)
            logger.debug(f"Đã upsert {len(batch)} points vào Qdrant (batch {i // batch_size + 1})")

        logger.info(f"Đã nạp thành công tổng cộng {total_upserted} points vào collection '{collection_name}'")
        return total_upserted

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        model: str | None = None,
        category: str | None = None,
        score_threshold: float | None = None,
    ) -> list[Any]:
        """Truy vấn tìm kiếm vector ngữ nghĩa kết hợp bộ lọc Metadata trong Qdrant."""
        must_conditions = []

        # 1. Bộ lọc dòng xe (Chống nhiễm chéo xe)
        if model and model != "ALL":
            must_conditions.append(
                FieldCondition(
                    key="model",
                    match=MatchValue(value=model),
                )
            )

        # 2. Bộ lọc phân loại hạng mục (bảo dưỡng, bảo hành...)
        if category and category not in ["all", "general"]:
            must_conditions.append(
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category),
                )
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        # Sử dụng API query_points (qdrant-client >= 1.10) hoặc search (cũ)
        if hasattr(self._client, "query_points"):
            res = self._client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
            )
            return res.points
        else:
            return getattr(self._client, "search")(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
            )

    def count(self, collection_name: str = settings.qdrant_collection_name) -> int:
        """Đếm tổng số vector trong collection."""
        try:
            res = self._client.count(collection_name=collection_name, exact=True)
            return res.count
        except Exception:
            return 0
