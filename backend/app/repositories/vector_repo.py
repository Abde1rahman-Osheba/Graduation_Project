"""
PATHS Backend — Qdrant vector repository.

Low-level operations for the candidate_cv_chunks collection.
"""

import logging
import uuid
import datetime
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_qdrant_client() -> QdrantClient:
    """Build a Qdrant client from settings."""
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=10,
    )


def init_collection():
    """Ensure the CV chunks collection exists, creating it if needed."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_cv
    vector_size = settings.qdrant_collection_vector_size

    if not client.collection_exists(collection_name):
        logger.info("Creating Qdrant collection '%s' (dim=%d)", collection_name, vector_size)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
    else:
        logger.info("Qdrant collection '%s' already exists", collection_name)


def upsert_chunks(
    candidate_id: str,
    document_id: str,
    chunks: List[str],
    embeddings: List[List[float]],
):
    """Upsert embedded CV chunks into Qdrant with full payload."""
    if not chunks or not embeddings:
        return

    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_cv

    points = []
    for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        payload = {
            "candidate_id": candidate_id,
            "document_id": document_id,
            "chunk_index": i,
            "text": chunk,
            "source_type": "cv",
            "version": "1.0",
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        points.append(
            PointStruct(id=point_id, vector=vector, payload=payload)
        )

    client.upsert(collection_name=collection_name, points=points)
    logger.info("Upserted %d vectors to '%s'", len(points), collection_name)


def search_chunks(
    candidate_id: str,
    query_vector: List[float],
    limit: int = 5,
) -> list:
    """Search for similar chunks for a given candidate."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_cv

    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="candidate_id", match=MatchValue(value=candidate_id))]
        ),
        limit=limit,
    )
    return [{"id": str(hit.id), "score": hit.score, "payload": hit.payload} for hit in results.points]


def count_chunks(candidate_id: str) -> int:
    """Count how many chunks exist for a given candidate."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_cv

    try:
        result = client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="candidate_id", match=MatchValue(value=candidate_id))]
            ),
        )
        return result.count
    except Exception:
        return 0
