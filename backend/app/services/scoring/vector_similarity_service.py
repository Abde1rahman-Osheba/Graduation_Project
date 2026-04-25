"""
PATHS Backend — Vector similarity service for scoring.

Implements the spec rules from
`PATHS_Candidate_Job_Scoring_Service_Cursor_Instructions.md` §11:

  * Qdrant candidate point ID == ``candidate_id``.
  * Qdrant job point ID == ``job_id``.
  * One candidate = one vector, one job = one vector.
  * Missing vector → similarity = 0.0 with status
    ``completed_with_vector_missing``. The whole run never crashes.
  * Cosine similarity is normalized from [-1, 1] → [0, 100].

The service deliberately does **not** create new vectors. It only
reads them via the existing repositories built in PR #1
(``candidates_vector`` / ``jobs_vector``).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Result containers ────────────────────────────────────────────────────


@dataclass
class VectorSimilarityResult:
    """Container returned by `compute_similarity_score`."""

    score: float                # 0..100
    cosine: float | None        # raw cosine in [-1, 1] (None when missing)
    candidate_vector_present: bool
    job_vector_present: bool
    status: str                 # "ok" | "completed_with_vector_missing"


# ── Internal Qdrant client ───────────────────────────────────────────────


def _client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=10,
    )


def _retrieve_vector(
    client: QdrantClient, *, collection: str, point_id: str,
) -> list[float] | None:
    try:
        records = client.retrieve(
            collection_name=collection,
            ids=[point_id],
            with_vectors=True,
            with_payload=False,
        )
    except (UnexpectedResponse, Exception):  # noqa: BLE001
        logger.exception(
            "vector_similarity: failed to fetch %s from %s",
            point_id, collection,
        )
        return None

    if not records:
        return None
    rec = records[0]
    vec = rec.vector
    if isinstance(vec, dict):
        # Named-vector collections return {"name": [...]}; pick the first
        if not vec:
            return None
        vec = next(iter(vec.values()))
    if not vec:
        return None
    return [float(x) for x in vec]


# ── Math helpers ─────────────────────────────────────────────────────────


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    """Compute cosine similarity between two equal-length numeric vectors."""
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list:
        return 0.0
    if len(a_list) != len(b_list):
        raise ValueError(
            f"vector dimension mismatch: {len(a_list)} vs {len(b_list)}"
        )
    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = math.sqrt(sum(x * x for x in a_list))
    norm_b = math.sqrt(sum(y * y for y in b_list))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    cos = dot / (norm_a * norm_b)
    # Numerical clean-up — cosine should be in [-1, 1]
    return max(-1.0, min(1.0, cos))


def normalize_to_score(cosine: float) -> float:
    """Map cosine ∈ [-1, 1] → score ∈ [0, 100]."""
    return round(max(0.0, (cosine + 1.0) / 2.0 * 100.0), 3)


# ── Public API ───────────────────────────────────────────────────────────


def compute_similarity_score(
    candidate_id: UUID | str,
    job_id: UUID | str,
    *,
    client: QdrantClient | None = None,
) -> VectorSimilarityResult:
    """Pull both vectors from Qdrant and return a 0–100 similarity score.

    Returns a `VectorSimilarityResult` with `score=0` and
    `status="completed_with_vector_missing"` when either vector is
    missing — the caller still gets a deterministic answer and the
    scoring run continues.
    """
    cli = client or _client()
    cand = _retrieve_vector(
        cli, collection=settings.qdrant_candidate_collection, point_id=str(candidate_id),
    )
    job = _retrieve_vector(
        cli, collection=settings.qdrant_job_collection, point_id=str(job_id),
    )

    if cand is None or job is None:
        return VectorSimilarityResult(
            score=0.0,
            cosine=None,
            candidate_vector_present=cand is not None,
            job_vector_present=job is not None,
            status="completed_with_vector_missing",
        )

    try:
        cos = cosine_similarity(cand, job)
    except ValueError:
        logger.exception("vector_similarity: dimension mismatch")
        return VectorSimilarityResult(
            score=0.0,
            cosine=None,
            candidate_vector_present=True,
            job_vector_present=True,
            status="completed_with_vector_missing",
        )

    return VectorSimilarityResult(
        score=normalize_to_score(cos),
        cosine=cos,
        candidate_vector_present=True,
        job_vector_present=True,
        status="ok",
    )


__all__ = [
    "VectorSimilarityResult",
    "compute_similarity_score",
    "cosine_similarity",
    "normalize_to_score",
]
