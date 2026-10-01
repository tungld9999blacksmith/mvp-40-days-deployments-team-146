"""
Qdrant Infrastructure Package — EV Care
"""

from .dependency import get_qdrant_service
from .qdrant_service import QdrantService

__all__ = ["QdrantService", "get_qdrant_service"]
