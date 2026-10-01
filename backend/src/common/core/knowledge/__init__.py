"""Knowledge domain: manufacturer documents, their chunks and rule evidence (RAG)."""

from .document_chunk import EMBEDDING_DIMENSIONS, DocumentChunk, DocumentChunkRepository
from .maintenance_rule_source import MaintenanceRuleSource, MaintenanceRuleSourceRepository
from .official_document import OfficialDocument, OfficialDocumentRepository, OfficialDocumentType

__all__ = [
    "DocumentChunk",
    "DocumentChunkRepository",
    "EMBEDDING_DIMENSIONS",
    "MaintenanceRuleSource",
    "MaintenanceRuleSourceRepository",
    "OfficialDocument",
    "OfficialDocumentRepository",
    "OfficialDocumentType",
]
