"""ENT-406 — OfficialDocument: metadata of a manufacturer document ingested for RAG.

Columns follow ``docs/specs/entity/knowledge/official_document.entity.md``.
The chunked content lives in ``document_chunk``.
"""

from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Column, Date, DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class OfficialDocumentType(str, Enum):
    OWNER_MANUAL = "owner_manual"
    MAINTENANCE_MANUAL = "maintenance_manual"
    WARRANTY_POLICY = "warranty_policy"
    SERVICE_BULLETIN = "service_bulletin"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class OfficialDocument(SQLModel, table=True):
    __tablename__ = "official_document"
    __table_args__ = (
        # NULLS NOT DISTINCT (PostgreSQL 15+): two rows with the same title and
        # no version are duplicates too (Q-407).
        UniqueConstraint(
            "title",
            "version",
            name="ux_official_document_title_version",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_official_document_model_type", "model_id", "document_type"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(sa_column=Column(String(255), nullable=False))
    # Manufacturer model code; NULL means the document applies to every model.
    model_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    document_type: OfficialDocumentType = Field(
        sa_column=Column(
            SQLEnum(
                OfficialDocumentType,
                name="official_document_type_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
        )
    )
    version: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    source_url: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    effective_date: date | None = Field(default=None, sa_column=Column(Date, nullable=True))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class OfficialDocumentRepository(SQLModelRepository[OfficialDocument, UUID]):
    model = OfficialDocument
