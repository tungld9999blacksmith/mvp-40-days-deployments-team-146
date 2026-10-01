from functools import lru_cache

from .chroma_service import ChromaService


@lru_cache
def get_chroma_service() -> ChromaService:
    return ChromaService()
