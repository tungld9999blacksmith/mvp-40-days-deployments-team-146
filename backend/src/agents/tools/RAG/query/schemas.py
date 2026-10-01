from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UserVehicleContext(BaseModel):
    """Thông tin ngữ cảnh xe của người dùng (từ phiên đăng nhập/database)."""

    brand: str = "VinFast"
    model: str | None = None
    year: int | None = None
    current_odometer_km: int | None = None
    battery_type: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class QueryAnalysis(BaseModel):
    """Kết quả phân tích, viết lại câu hỏi và trích xuất bộ lọc metadata (bởi LLM)."""

    original_query: str = Field(..., description="Câu hỏi gốc của người dùng")
    rewritten_query: str = Field(
        ...,
        description="Câu hỏi đã được chuẩn hóa, mở rộng ngữ cảnh xe điện và bỏ đại từ mơ hồ",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Danh sách từ khóa quan trọng phục vụ tìm kiếm từ vựng (BM25)",
    )
    model: str | None = None
    category: str | None = None
    milestone_km: int | None = None
    subsystem: str | None = None
    is_out_of_scope: bool = False


class RetrievalCandidate(BaseModel):
    """Đại diện cho một đoạn văn bản (chunk) được tìm thấy qua các bước lọc và xếp hạng."""

    chunk_id: str
    doc_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    dense_score: float | None = None
    sparse_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class CitationItem(BaseModel):
    """Trích dẫn tài liệu chuẩn xác có cấu trúc để frontend render nguồn tham chiếu."""

    document_id: str = Field(..., description="ID định danh tài liệu gốc")
    title: str = Field(..., description="Tiêu đề tài liệu chính hãng")
    section: str = Field(default="", description="Tiêu đề mục / chương chứa thông tin")
    source_url: str | None = Field(None, description="Đường link tài liệu (nếu có)")
    chunk_id: str = Field(..., description="ID định danh chunk cụ thể")
    score: float | None = Field(None, description="Điểm độ tương quan sau khi rerank")


class RAGResponse(BaseModel):
    """Quy chuẩn dữ liệu đầu ra hoàn chỉnh của hệ thống RAG trả về cho người dùng/API."""

    answer: str = Field(..., description="Nội dung câu trả lời có căn cứ tài liệu")
    citations: list[CitationItem] = Field(
        default_factory=list,
        description="Danh sách các trích dẫn nguồn chính hãng hỗ trợ câu trả lời",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        "high",
        description="Mức độ tin cậy của câu trả lời dựa trên điểm số tài liệu",
    )
    fallback_required: bool = Field(
        False,
        description="True nếu không đủ tài liệu chính hãng hoặc câu hỏi vượt quá phạm vi hỗ trợ",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Thông tin kỹ thuật bổ sung (rewritten_query, latency, execution_stats)",
    )
