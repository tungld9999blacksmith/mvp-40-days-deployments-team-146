"""ENT-407 — DocumentChunk: a chunk of an official document with its embedding.

Columns follow ``docs/specs/entity/knowledge/document_chunk.entity.md``.
Append-only: re-ingesting a document replaces all of its chunks (BR-ENT-409),
so there is no ``updated_at``. Every chunk uses the same 1024-dim embedding
model (Q-408, BR-ENT-410).
"""

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository

EMBEDDING_DIMENSIONS = 1024


class DocumentChunk(SQLModel, table=True):
    __tablename__ = "document_chunk"
    __table_args__ = (
        CheckConstraint("chunk_index >= 0", name="ck_document_chunk_chunk_index"),
        CheckConstraint(
            "page_number IS NULL OR page_number > 0", name="ck_document_chunk_page_number"
        ),
        UniqueConstraint("document_id", "chunk_index", name="ux_document_chunk_document_index"),
        # ANN index for semantic search (cosine distance).
        Index(
            "ix_document_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    document_id: UUID = Field(
        sa_column=Column(
            ForeignKey("official_document.id", ondelete="CASCADE"), nullable=False
        )
    )
    chunk_index: int = Field(sa_column=Column(Integer, nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    page_number: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    embedding: list[float] = Field(
        sa_column=Column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    )

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class DocumentChunkRepository(SQLModelRepository[DocumentChunk, UUID]):
    model = DocumentChunk
