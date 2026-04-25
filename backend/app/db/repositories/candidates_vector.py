"""
PATHS Backend — Candidate vector repository (Qdrant).

Implements the spec rule: **one candidate = one Qdrant point**, with the
PostgreSQL `candidate_id` UUID used as both the point ID and the
`payload.candidate_id` field.
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


def ensure_candidate_collection(vector_size: int | None = None) -> dict[str, Any]:
    """Create the candidate collection if it does not exist."""
    name = settings.qdrant_candidate_collection
    size = vector_size or settings.embedding_dimension
    client = _client()
    try:
        info = client.get_collection(name)
        existing_size = info.config.params.vectors.size  # type: ignore[union-attr]
        if existing_size and size and existing_size != size:
            raise RuntimeError(
                f"Candidate collection '{name}' has dim {existing_size} "
                f"but embedding model produces dim {size}. Refusing to corrupt."
            )
        return {"collection": name, "action": "exists", "dimension": existing_size}
    except (UnexpectedResponse, Exception) as exc:  # noqa: BLE001
        # Collection missing or generic 404
        logger.info("Creating Qdrant candidate collection '%s' (dim=%d)", name, size)
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


def upsert_candidate_vector(
    candidate_id: UUID | str,
    vector: list[float],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Upsert exactly one Qdrant point for a candidate."""
    cid = str(candidate_id)
    payload = {**payload, "candidate_id": cid, "entity_type": "candidate"}
    client = _client()
    point = PointStruct(id=cid, vector=vector, payload=payload)
    client.upsert(
        collection_name=settings.qdrant_candidate_collection, points=[point],
    )
    return {"upserted": 1, "point_id": cid}


def get_candidate_point(candidate_id: UUID | str) -> dict[str, Any] | None:
    cid = str(candidate_id)
    client = _client()
    try:
        result = client.retrieve(
            collection_name=settings.qdrant_candidate_collection,
            ids=[cid],
            with_payload=True,
            with_vectors=False,
        )
    except (UnexpectedResponse, Exception):  # noqa: BLE001
        return None
    if not result:
        return None
    p = result[0]
    return {"id": str(p.id), "payload": p.payload}


def delete_candidate_vector(candidate_id: UUID | str) -> int:
    client = _client()
    client.delete(
        collection_name=settings.qdrant_candidate_collection,
        points_selector=[str(candidate_id)],
    )
    return 1


def search_candidates_for_job(
    query_vector: list[float],
    *,
    top_k: int = 20,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    must = [FieldCondition(key="entity_type", match=MatchValue(value="candidate"))]
    if filters:
        for k, v in filters.items():
            must.append(FieldCondition(key=k, match=MatchValue(value=v)))
    qfilter = Filter(must=must)

    client = _client()
    res = client.query_points(
        collection_name=settings.qdrant_candidate_collection,
        query=query_vector,
        limit=top_k,
        query_filter=qfilter,
    )
    return [
        {"id": str(hit.id), "score": hit.score, "payload": hit.payload}
        for hit in res.points
    ]


def verify_one_vector_per_candidate(candidate_id: UUID | str) -> dict[str, Any]:
    """Confirm there is exactly one Qdrant point for this candidate."""
    cid = str(candidate_id)
    client = _client()
    try:
        # Count by payload.candidate_id (catches accidental duplicates)
        counted = client.count(
            collection_name=settings.qdrant_candidate_collection,
            count_filter=Filter(
                must=[
                    FieldCondition(key="candidate_id", match=MatchValue(value=cid)),
                ]
            ),
            exact=True,
        ).count
    except (UnexpectedResponse, Exception):  # noqa: BLE001
        counted = 0

    point = get_candidate_point(cid)
    return {
        "candidate_id": cid,
        "collection": settings.qdrant_candidate_collection,
        "exists": point is not None,
        "point_id": point["id"] if point else None,
        "payload_candidate_id": (point or {}).get("payload", {}).get("candidate_id"),
        "vector_count_for_candidate": counted,
        "embedding_model": (point or {}).get("payload", {}).get("embedding_model"),
        "source_hash": (point or {}).get("payload", {}).get("source_hash"),
        "unified_id_valid": (
            point is not None
            and point["id"] == cid
            and (point.get("payload") or {}).get("candidate_id") == cid
            and counted == 1
        ),
    }
