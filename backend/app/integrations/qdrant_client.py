"""
PATHS Backend — Qdrant client factory.

Produces a configured QdrantClient instance and a FastAPI dependency.
"""

from functools import lru_cache

from qdrant_client import QdrantClient

from app.core.config import get_settings

settings = get_settings()


@lru_cache
def get_qdrant_client() -> QdrantClient:
    """Return a singleton Qdrant client."""
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=10,
    )
