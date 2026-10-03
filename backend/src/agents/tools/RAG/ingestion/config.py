from __future__ import annotations

from pydantic import BaseModel, Field


class RAGSettings(BaseModel):
    chunk_size: int = Field(default=800, description="Kích thước tối đa của mỗi chunk")
    chunk_overlap: int = Field(default=150, description="Độ chồng lấp giữa 2 chunk liên tiếp")
    vector_collection_name: str = Field(default="ev_care_knowledge_base")
    embedding_model_name: str = Field(default="models/gemini-embedding-001")
    openai_embedding_model: str = Field(default="text-embedding-3-small")


rag_settings = RAGSettings()
