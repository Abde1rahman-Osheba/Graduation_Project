"""
PATHS Backend — Qdrant vector-database service layer.

Manages collections, vector upsert, and similarity search
against the Qdrant instance.
"""

from typing import Any
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class QdrantService:
    """High-level Qdrant operations for PATHS."""

    def __init__(self, client: QdrantClient | None = None) -> None:
        self._client = client or self._build_client()

    @staticmethod
    def _build_client() -> QdrantClient:
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=10,
        )

    @property
    def client(self) -> QdrantClient:
        return self._client

    # ── Health ─────────────────────────────────────────────────────────

    def test_connection(self) -> dict:
        """Ping Qdrant and return cluster info."""
        try:
            info = self._client.get_collections()
            collection_names = [c.name for c in info.collections]
            logger.info("Qdrant connected — %d collections", len(collection_names))
            return {
                "status": "healthy",
                "collections_count": len(collection_names),
                "collections": collection_names,
            }
        except Exception as exc:
            logger.error("Qdrant connection failed: %s", exc)
            return {"status": "unhealthy", "error": str(exc)}

    # ── Collection management ──────────────────────────────────────────

    def init_collections(self, vector_size: int | None = None) -> dict:
        """Create the CV chunks collection if it does not exist."""
        size = vector_size or settings.qdrant_collection_vector_size
        collection_name = settings.qdrant_collection_cv

        try:
            self._client.get_collection(collection_name)
            logger.info("Collection '%s' already exists", collection_name)
            return {"status": "ok", "collection": collection_name, "action": "exists"}
        except (UnexpectedResponse, Exception):
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=size, distance=Distance.COSINE),
            )
            logger.info("Collection '%s' created (dim=%d)", collection_name, size)
            return {"status": "ok", "collection": collection_name, "action": "created"}

    def list_collections(self) -> list[str]:
        """Return the names of all existing collections."""
        info = self._client.get_collections()
        return [c.name for c in info.collections]

    # ── Vector operations ──────────────────────────────────────────────

    def upsert_vectors(
        self,
        collection_name: str,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: list[str] | None = None,
    ) -> dict:
        """Upsert a batch of vectors with associated payloads."""
        if ids is None:
            ids = [str(uuid4()) for _ in vectors]

        points = [
            PointStruct(id=pid, vector=vec, payload=pay)
            for pid, vec, pay in zip(ids, vectors, payloads)
        ]
        self._client.upsert(collection_name=collection_name, points=points)
        logger.info("Upserted %d vectors to '%s'", len(points), collection_name)
        return {"upserted": len(points), "collection": collection_name}

    def search_vectors(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Run a similarity search, optionally filtered by payload fields."""
        qdrant_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            qdrant_filter = Filter(must=conditions)

        results = self._client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
        )
        return [
            {"id": str(hit.id), "score": hit.score, "payload": hit.payload}
            for hit in results.points
        ]
