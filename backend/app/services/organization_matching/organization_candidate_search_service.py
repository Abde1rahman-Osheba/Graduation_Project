"""
Path A — discover relevant candidates from the existing database using
Qdrant (job → candidate search) + PostgreSQL + relevance gating.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.repositories import candidates_relational, jobs_relational, jobs_vector
from app.db.repositories.candidates_vector import search_candidates_for_job
from app.services.embedding_service import embed_query
from app.services.scoring.relevance_filter_service import assess_relevance, candidate_role_family
from app.services.scoring.relevance_filter_service import job_role_family
from app.services.vector_text_builders import build_job_vector_text

logger = logging.getLogger(__name__)
settings = get_settings()


def discover_candidates_for_job(
    db: Session,
    job_id: UUID,
    *,
    max_pool: int | None = None,
) -> tuple[list[UUID], dict[str, int]]:
    """
    Return shuffled-ordered list of candidate IDs worth scoring, capped
    at ``ORG_MATCHING_MAX_CANDIDATES_PER_RUN`` (or `max_pool`).
    """
    cap = max_pool or settings.org_matching_max_candidates_per_run
    cap = max(1, int(cap))

    prof = jobs_relational.get_job_full_profile(db, job_id)
    if prof is None:
        return [], {"qdrant_hits": 0, "pg_scanned": 0, "passed_filter": 0}

    j_family = job_role_family(prof)
    vec = jobs_vector.get_job_vector(job_id)
    if not vec:
        # Repair path: embed from canonical text
        try:
            text = build_job_vector_text(prof)
            vec = embed_query(text) or []
        except Exception:  # noqa: BLE001
            vec = []
    if not vec:
        logger.warning("[OrgSearch] no job vector for %s — falling back to PG list only", job_id)

    q_hits: list[UUID] = []
    if vec:
        raw = search_candidates_for_job(
            vec, top_k=min(cap * 3, 500),
        )
        for h in raw:
            try:
                q_hits.append(UUID(str(h["id"])))
            except Exception:  # noqa: BLE001
                continue

    seen: set[UUID] = set(q_hits)
    extra = candidates_relational.list_active_candidate_ids(db, limit=cap * 2)
    ordered: list[UUID] = list(q_hits)
    for e in extra:
        if e not in seen:
            seen.add(e)
            ordered.append(e)
        if len(ordered) >= cap * 2:
            break

    j_profile = prof
    thr = float(settings.org_scoring_min_relevance_threshold)
    passed: list[UUID] = []
    for cid in ordered:
        if len(passed) >= cap:
            break
        cprof = candidates_relational.get_candidate_full_profile(db, cid)
        if cprof is None:
            continue
        from app.services.scoring.vector_similarity_service import compute_similarity_score

        sim = compute_similarity_score(cid, job_id)
        sim_score = sim.score
        dec = assess_relevance(
            cprof,
            j_profile,
            candidate_family=candidate_role_family(cprof),
            vector_similarity_score=sim_score,
            min_relevance_threshold=thr,
        )
        if not dec.is_relevant:
            continue
        passed.append(cid)

    stats = {
        "qdrant_hits": len(q_hits),
        "pg_scanned": len(ordered),
        "passed_filter": len(passed),
    }
    return passed, stats
