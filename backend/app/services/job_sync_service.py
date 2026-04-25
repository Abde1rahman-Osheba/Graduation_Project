"""
PATHS Backend — Job synchronization service.

Mirror of `candidate_sync_service` but for jobs:

  PostgreSQL (canonical) → Apache AGE → Qdrant (one vector per job)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.repositories import (
    jobs_graph,
    jobs_relational,
    jobs_vector,
    sync_status,
)
from app.services.embedding_service import embed_query
from app.services.vector_text_builders import (
    build_job_vector_text,
    text_source_hash,
)
from app.utils.age_query import ensure_graph

logger = logging.getLogger(__name__)
settings = get_settings()


def _build_job_payload(
    profile: jobs_relational.JobFullProfile, *, source_hash: str,
) -> dict[str, Any]:
    j = profile.job
    skills = [jsr.skill_name_normalized for jsr, _ in profile.skill_requirements]
    return {
        "job_id": str(j.id),
        "organization_id": str(j.organization_id) if j.organization_id else None,
        "company_id": str(profile.company.id) if profile.company else None,
        "entity_type": "job",
        "source": j.source_type or "manual",
        "source_hash": source_hash,
        "embedding_model": settings.embedding_model,
        "embedding_version": settings.embedding_version,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": j.status or "draft",
        "title": j.title or "",
        "seniority_level": j.seniority_level or "",
        "employment_type": j.employment_type or "",
        "work_mode": j.location_mode or "",
        "skills": skills,
        "location": j.location_text or "",
    }


def sync_job_to_graph(db: Session, job_id: UUID | str) -> dict[str, Any]:
    jid = str(job_id)
    profile = jobs_relational.get_job_full_profile(db, jid)
    if profile is None:
        sync_status.mark_graph_failed(db, "job", jid, error="job not found")
        return {"status": "error", "error": "job_not_found"}

    try:
        ensure_graph(db)
        jobs_graph.upsert_job_node(db, profile)
        skills = jobs_graph.upsert_job_required_skills(db, profile)
        org = jobs_graph.upsert_job_organization_edge(db, profile)
        sync_status.mark_graph_success(db, "job", jid)
        sync_status.write_audit_log(
            db,
            action="job.graph_synced",
            entity_type="job",
            entity_id=jid,
            metadata={"required_skills": skills, "organization_edge": org},
        )
        db.commit()
        return {"status": "success", "required_skills": skills, "organization_edge": org}
    except Exception as exc:
        db.rollback()
        logger.exception("job graph sync failed for %s", jid)
        sync_status.mark_graph_failed(db, "job", jid, error=str(exc))
        sync_status.write_audit_log(
            db,
            action="sync.failed",
            entity_type="job",
            entity_id=jid,
            metadata={"layer": "graph", "error": str(exc)[:500]},
        )
        db.commit()
        return {"status": "error", "error": str(exc)}


def sync_job_to_vector(
    db: Session, job_id: UUID | str, *, force: bool = False,
) -> dict[str, Any]:
    jid = str(job_id)
    profile = jobs_relational.get_job_full_profile(db, jid)
    if profile is None:
        sync_status.mark_vector_failed(db, "job", jid, error="job not found")
        return {"status": "error", "error": "job_not_found"}

    try:
        jobs_vector.ensure_job_collection()
        text = build_job_vector_text(profile)
        h = text_source_hash(text)

        existing = jobs_vector.get_job_point(jid)
        if (
            not force
            and existing is not None
            and (existing.get("payload") or {}).get("source_hash") == h
        ):
            sync_status.mark_vector_success(db, "job", jid, source_hash=h)
            db.commit()
            return {"status": "unchanged", "source_hash": h}

        vector = embed_query(text)
        if not vector:
            raise RuntimeError("embedding model returned empty vector")
        payload = _build_job_payload(profile, source_hash=h)
        jobs_vector.upsert_job_vector(jid, vector, payload)
        sync_status.mark_vector_success(db, "job", jid, source_hash=h)
        sync_status.write_audit_log(
            db,
            action="job.vector_synced",
            entity_type="job",
            entity_id=jid,
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
        logger.exception("job vector sync failed for %s", jid)
        sync_status.mark_vector_failed(db, "job", jid, error=str(exc))
        sync_status.write_audit_log(
            db,
            action="sync.failed",
            entity_type="job",
            entity_id=jid,
            metadata={"layer": "vector", "error": str(exc)[:500]},
        )
        db.commit()
        return {"status": "error", "error": str(exc)}


def sync_job_full(
    db: Session, job_id: UUID | str, *, force_vector: bool = False,
) -> dict[str, Any]:
    g = sync_job_to_graph(db, job_id)
    v = sync_job_to_vector(db, job_id, force=force_vector)
    return {"graph": g, "vector": v}
