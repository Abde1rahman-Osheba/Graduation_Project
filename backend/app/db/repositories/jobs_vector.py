"""
PATHS Backend — Job vector repository (Qdrant).

Implements the spec rule: **one job = one Qdrant point**, with the
PostgreSQL `job_id` UUID used as both the point ID and the
`payload.job_id` field.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

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

logger = logging.getLogger(__name__)
settings = get_settings()


def _client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=10,
    )


def ensure_job_collection(vector_size: int | None = None) -> dict[str, Any]:
    name = settings.qdrant_job_collection
    size = vector_size or settings.embedding_dimension
    client = _client()
    try:
        info = client.get_collection(name)
        existing_size = info.config.params.vectors.size  # type: ignore[union-attr]
        if existing_size and size and existing_size != size:
            raise RuntimeError(
                f"Job collection '{name}' has dim {existing_size} but model "
                f"produces dim {size}. Refusing to corrupt."
            )
        return {"collection": name, "action": "exists", "dimension": existing_size}
    except (UnexpectedResponse, Exception) as exc:  # noqa: BLE001
        logger.info("Creating Qdrant job collection '%s' (dim=%d)", name, size)
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )
        return {
            "collection": name,
            "action": "created",
            "dimension": size,
            "previous_error": str(exc) if not isinstance(exc, UnexpectedResponse) else None,
        }


def upsert_job_vector(
    job_id: UUID | str,
    vector: list[float],
    payload: dict[str, Any],
) -> dict[str, Any]:
    jid = str(job_id)
    payload = {**payload, "job_id": jid, "entity_type": "job"}
    client = _client()
    point = PointStruct(id=jid, vector=vector, payload=payload)
    client.upsert(collection_name=settings.qdrant_job_collection, points=[point])
    return {"upserted": 1, "point_id": jid}


def get_job_point(job_id: UUID | str) -> dict[str, Any] | None:
    jid = str(job_id)
    client = _client()
    try:
        result = client.retrieve(
            collection_name=settings.qdrant_job_collection,
            ids=[jid],
            with_payload=True,
            with_vectors=False,
        )
    except (UnexpectedResponse, Exception):  # noqa: BLE001
        return None
    if not result:
        return None
    p = result[0]
    return {"id": str(p.id), "payload": p.payload}


def get_job_vector(job_id: UUID | str) -> list[float] | None:
    """Return the dense embedding for this job, or None if missing."""
    jid = str(job_id)
    client = _client()
    try:
        result = client.retrieve(
            collection_name=settings.qdrant_job_collection,
            ids=[jid],
            with_payload=False,
            with_vectors=True,
        )
    except (UnexpectedResponse, Exception):  # noqa: BLE001
        return None
    if not result:
        return None
    p = result[0]
    vec = p.vector
    if isinstance(vec, dict):
        # Named vectors: take first
        for _k, v in vec.items():
            if isinstance(v, list):
                return v
        return None
    if isinstance(vec, list):
        return vec
    return None


def delete_job_vector(job_id: UUID | str) -> int:
    client = _client()
    client.delete(
        collection_name=settings.qdrant_job_collection,
        points_selector=[str(job_id)],
    )
    return 1


def search_jobs_for_candidate(
    query_vector: list[float],
    *,
    top_k: int = 20,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    must = [FieldCondition(key="entity_type", match=MatchValue(value="job"))]
    if filters:
        for k, v in filters.items():
            must.append(FieldCondition(key=k, match=MatchValue(value=v)))
    qfilter = Filter(must=must)
    client = _client()
    res = client.query_points(
        collection_name=settings.qdrant_job_collection,
        query=query_vector,
        limit=top_k,
        query_filter=qfilter,
    )
    return [
        {"id": str(hit.id), "score": hit.score, "payload": hit.payload}
        for hit in res.points
    ]


def verify_one_vector_per_job(job_id: UUID | str) -> dict[str, Any]:
    jid = str(job_id)
    client = _client()
    try:
        counted = client.count(
            collection_name=settings.qdrant_job_collection,
            count_filter=Filter(
                must=[FieldCondition(key="job_id", match=MatchValue(value=jid))]
            ),
            exact=True,
        ).count
    except (UnexpectedResponse, Exception):  # noqa: BLE001
        counted = 0

    point = get_job_point(jid)
    return {
        "job_id": jid,
        "collection": settings.qdrant_job_collection,
        "exists": point is not None,
        "point_id": point["id"] if point else None,
        "payload_job_id": (point or {}).get("payload", {}).get("job_id"),
        "vector_count_for_job": counted,
        "embedding_model": (point or {}).get("payload", {}).get("embedding_model"),
        "source_hash": (point or {}).get("payload", {}).get("source_hash"),
        "unified_id_valid": (
            point is not None
            and point["id"] == jid
            and (point.get("payload") or {}).get("job_id") == jid
            and counted == 1
        ),
    }
