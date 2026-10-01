"""
Bridge an `EmbeddingEngine` to `langchain_core.embeddings.Embeddings`.

LangGraph nodes, LangChain retrievers and LangChain vector stores expect an
object with `embed_documents` / `embed_query` (+ async variants). Our engine
already exposes exactly those names, so this adapter only re-declares the base
class for isinstance/type checks and keeps the rest of the app decoupled from
LangChain.

    from langchain_core.vectorstores import InMemoryVectorStore
    store = InMemoryVectorStore(LangChainEmbeddings(get_embedding_engine()))
"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings

from .base import EmbeddingEngine


class LangChainEmbeddings(Embeddings):
    def __init__(self, engine: EmbeddingEngine) -> None:
        self._engine = engine

    @property
    def engine(self) -> EmbeddingEngine:
        return self._engine

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._engine.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._engine.embed_query(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._engine.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await self._engine.aembed_query(text)
