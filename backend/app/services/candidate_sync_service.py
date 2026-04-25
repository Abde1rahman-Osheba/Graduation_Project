"""
PATHS Backend — Candidate synchronization service.

Orchestrates the spec-required candidate sync flow:

  PostgreSQL (canonical) → Apache AGE → Qdrant (one vector)

Each sub-step is captured in `db_sync_status` and an `audit_logs` row is
written. Failures in graph or vector sync do **not** delete the
PostgreSQL row — they are recorded so the admin retry endpoints can
recover the candidate later.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.repositories import (
    candidates_graph,
    candidates_relational,
    candidates_vector,
    sync_status,
)
from app.services.embedding_service import embed_query
from app.services.vector_text_builders import (
    build_candidate_vector_text,
    text_source_hash,
)
from app.utils.age_query import ensure_graph

logger = logging.getLogger(__name__)
settings = get_settings()


def _build_candidate_payload(
    profile: candidates_relational.CandidateFullProfile, *, source_hash: str,
) -> dict[str, Any]:
    c = profile.candidate
    skills = [sk.normalized_name for _, sk in profile.skills]
    location = c.location_text or ""
    return {
        "candidate_id": str(c.id),
        "entity_type": "candidate",
        "source": "ingestion",
        "source_hash": source_hash,
        "embedding_model": settings.embedding_model,
        "embedding_version": settings.embedding_version,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "open_to_work": True,
        "years_of_experience": float(c.years_experience or 0),
        "current_title": c.current_title or "",
        "skills": skills,
        "location": location,
    }


def sync_candidate_to_graph(
    db: Session, candidate_id: UUID | str,
) -> dict[str, Any]:
    """Project a candidate (and all related entities) into Apache AGE."""
    cid = str(candidate_id)
    profile = candidates_relational.get_candidate_full_profile(db, cid)
    if profile is None:
        sync_status.mark_graph_failed(
            db, "candidate", cid, error="candidate not found",
        )
        return {"status": "error", "error": "candidate_not_found"}

    try:
        ensure_graph(db)
        candidates_graph.upsert_candidate_node(db, profile)
        skills = candidates_graph.upsert_candidate_skills(db, profile)
        exps = candidates_graph.upsert_candidate_experiences(db, profile)
        edu = candidates_graph.upsert_candidate_education(db, profile)
        proj = candidates_graph.upsert_candidate_projects(db, profile)
        certs = candidates_graph.upsert_candidate_certifications(db, profile)
        sync_status.mark_graph_success(db, "candidate", cid)
        sync_status.write_audit_log(
            db,
            action="candidate.graph_synced",
            entity_type="candidate",
            entity_id=cid,
            metadata={
                "skills": skills,
                "experiences": exps,
                "education": edu,
                "projects": proj,
                "certifications": certs,
            },
        )
        db.commit()
        return {
            "status": "success",
            "skills": skills,
            "experiences": exps,
            "education": edu,
            "projects": proj,
            "certifications": certs,
        }
    except Exception as exc:
        db.rollback()
        logger.exception("candidate graph sync failed for %s", cid)
        sync_status.mark_graph_failed(db, "candidate", cid, error=str(exc))
        sync_status.write_audit_log(
            db,
            action="sync.failed",
            entity_type="candidate",
            entity_id=cid,
            metadata={"layer": "graph", "error": str(exc)[:500]},
        )
        db.commit()
        return {"status": "error", "error": str(exc)}


def sync_candidate_to_vector(
    db: Session, candidate_id: UUID | str, *, force: bool = False,
) -> dict[str, Any]:
    """Build the candidate vector text and upsert one Qdrant point."""
    cid = str(candidate_id)
    profile = candidates_relational.get_candidate_full_profile(db, cid)
    if profile is None:
        sync_status.mark_vector_failed(
            db, "candidate", cid, error="candidate not found",
        )
        return {"status": "error", "error": "candidate_not_found"}

    try:
        candidates_vector.ensure_candidate_collection()
        text = build_candidate_vector_text(profile)
        h = text_source_hash(text)

        existing = candidates_vector.get_candidate_point(cid)
        if (
            not force
            and existing is not None
            and (existing.get("payload") or {}).get("source_hash") == h
        ):
            sync_status.mark_vector_success(db, "candidate", cid, source_hash=h)
            db.commit()
            return {"status": "unchanged", "source_hash": h}

        vector = embed_query(text)
        if not vector:
            raise RuntimeError("embedding model returned empty vector")
        payload = _build_candidate_payload(profile, source_hash=h)
        candidates_vector.upsert_candidate_vector(cid, vector, payload)
        sync_status.mark_vector_success(db, "candidate", cid, source_hash=h)
        sync_status.write_audit_log(
            db,
            action="candidate.vector_synced",
            entity_type="candidate",
            entity_id=cid,
            metadata={
                "source_hash": h,
                "embedding_model": settings.embedding_model,
                "vector_dimension": len(vector),
            },
        )
        db.commit()
        return {
            "status": "success",
            "source_hash": h,
            "vector_dimension": len(vector),
        }
    except Exception as exc:
        db.rollback()
        logger.exception("candidate vector sync failed for %s", cid)
        sync_status.mark_vector_failed(db, "candidate", cid, error=str(exc))
        sync_status.write_audit_log(
            db,
            action="sync.failed",
            entity_type="candidate",
            entity_id=cid,
            metadata={"layer": "vector", "error": str(exc)[:500]},
        )
        db.commit()
        return {"status": "error", "error": str(exc)}


def sync_candidate_full(
    db: Session, candidate_id: UUID | str, *, force_vector: bool = False,
) -> dict[str, Any]:
    """Run both graph and vector sync. PostgreSQL is never modified here."""
    g = sync_candidate_to_graph(db, candidate_id)
    v = sync_candidate_to_vector(db, candidate_id, force=force_vector)
    return {"graph": g, "vector": v}
