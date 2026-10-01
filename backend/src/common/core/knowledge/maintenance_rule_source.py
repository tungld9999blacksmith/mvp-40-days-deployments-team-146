"""ENT-408 — MaintenanceRuleSource: which document chunks prove which maintenance item.

Columns follow ``docs/specs/entity/knowledge/maintenance_rule_source.entity.md``.
Many-to-many bridge between ``maintenance_rule`` and ``document_chunk``;
append-only (BR-ENT-420).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class MaintenanceRuleSource(SQLModel, table=True):
    __tablename__ = "maintenance_rule_source"
    __table_args__ = (
        UniqueConstraint(
            "maintenance_rule_id",
            "document_chunk_id",
            name="ux_maintenance_rule_source_rule_chunk",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    maintenance_rule_id: UUID = Field(
        sa_column=Column(
            ForeignKey("maintenance_rule.id", ondelete="CASCADE"), nullable=False
        )
    )
    document_chunk_id: UUID = Field(
        sa_column=Column(
            ForeignKey("document_chunk.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class MaintenanceRuleSourceRepository(SQLModelRepository[MaintenanceRuleSource, UUID]):
    model = MaintenanceRuleSource
