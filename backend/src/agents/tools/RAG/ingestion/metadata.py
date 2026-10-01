from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    source: str
    doc_id: str
    title: str
    file_type: Literal["pdf", "html", "md", "txt", "unknown"] = "unknown"
    model: str = "ALL"  # e.g. "VF5", "VF6", "VF7", "VF8", "VF9", "ALL"
    category: str = "general"  # "maintenance", "warranty", "pricing", "safety", "battery", "procedure"
    milestone_km: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = Field(default_factory=dict)


class RawDocument(BaseModel):
    doc_id: str
    content: str
    raw_bytes: bytes | None = None
    metadata: DocumentMetadata


class CleanedDocument(BaseModel):
    doc_id: str
    cleaned_content: str
    metadata: DocumentMetadata
    char_count: int
    word_count: int


class DocumentChunk(BaseModel):
    chunk_id: str
    doc_id: str
    content: str
    metadata: dict[str, Any]
    chunk_index: int
    total_chunks: int


class SearchResult(BaseModel):
    chunk_id: str
    content: str
    metadata: dict[str, Any]
    score: float | None = None  # Distance or similarity


class PipelineResult(BaseModel):
    status: Literal["success", "failed", "partial"]
    files_ingested: int
    cleaned_documents: int
    chunks_created: int
    vectors_indexed: int
    duration_seconds: float
    details: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
