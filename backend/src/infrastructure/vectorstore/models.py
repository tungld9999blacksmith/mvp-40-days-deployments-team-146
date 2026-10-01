"""Generic pgvector-backed embedding table shared by all collections.

One row per stored item. `collection` is the logical namespace (the Qdrant
"collection" equivalent). The `embedding` column is sized to
`settings.embedding_dimensions`; changing that setting requires a migration
that rebuilds this column and its index.

This is the *generic* store used via the `VectorStore` interface. Entity-owned
embeddings that need their own columns/constraints (e.g. ``document_chunk``)
keep their dedicated tables.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from ...config import get_settings

VECTOR_DIM = get_settings().embedding_dimensions


class VectorEmbedding(SQLModel, table=True):
    __tablename__ = "vector_embedding"
    __table_args__ = (
        Index("ix_vector_embedding_collection", "collection"),
        Index(
            "ix_vector_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: str = Field(sa_column=Column(String(255), primary_key=True))
    collection: str = Field(sa_column=Column(String(255), nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    # Attribute is `meta` because SQLModel reserves the name `metadata`.
    meta: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSONB, nullable=False, server_default="{}"),
    )
    embedding: list[float] = Field(sa_column=Column(Vector(VECTOR_DIM), nullable=False))
    # "<provider>:<model>" that produced `embedding`. All vectors in one
    # collection must share a model (same dimension is not enough for cosine).
    embedding_model: str | None = Field(
        default=None, sa_column=Column("embedding_model", String(128), nullable=True)
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
