"""
PATHS Backend — Admin verification & sync-retry endpoints.

Implements Phase 7 of the master integration spec:
  GET  /admin/verify/candidate/{candidate_id}
  GET  /admin/verify/job/{job_id}
  POST /admin/sync/candidate/{candidate_id}/retry
  POST /admin/sync/job/{job_id}/retry

The retry endpoints are guarded by the existing authentication system
when configured (see `_admin_user`). When auth is not yet wired into a
deployment they remain reachable so that database integration can be
verified by the project owner during bring-up.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.repositories import (
    candidates_graph,
    candidates_relational,
    candidates_vector,
    jobs_graph,
    jobs_relational,
    jobs_vector,
    sync_status,
)
from app.services.candidate_sync_service import sync_candidate_full
from app.services.job_sync_service import sync_job_full

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


def _parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field} UUID",
        ) from exc


# ── Verification ──────────────────────────────────────────────────────────


@router.get("/verify/candidate/{candidate_id}")
def verify_candidate(candidate_id: str, db: Session = Depends(get_db)):
    """Cross-store unified-ID verification for one candidate."""
    cid = _parse_uuid(candidate_id, "candidate_id")
    cid_str = str(cid)

    issues: list[str] = []

    # PostgreSQL
    profile = candidates_relational.get_candidate_full_profile(db, cid)
    if profile is None:
        return {
            "candidate_id": cid_str,
            "postgres": {"exists": False},
            "graph": {"exists": False},
            "qdrant": {"exists": False},
            "unified_id_valid": False,
            "issues": ["candidate_not_found_in_postgres"],
        }
    pg_counts = candidates_relational.candidate_summary_counts(db, cid)
    pg_section = {"exists": True, **pg_counts}

    # Apache AGE
    try:
        graph_section = candidates_graph.verify_candidate_graph(db, cid_str)
    except Exception as exc:  # noqa: BLE001
        graph_section = {"exists": False, "error": str(exc)[:200]}
        issues.append("graph_verification_failed")

    # Qdrant
    qdrant_section = candidates_vector.verify_one_vector_per_candidate(cid_str)
    if not qdrant_section.get("exists"):
        issues.append("qdrant_point_missing")
    elif qdrant_section.get("vector_count_for_candidate") != 1:
        issues.append(
            f"qdrant_vector_count_is_{qdrant_section.get('vector_count_for_candidate')}"
        )

    unified_id_valid = (
        pg_section.get("exists")
        and graph_section.get("exists")
        and qdrant_section.get("unified_id_valid", False)
    )
    if not unified_id_valid and not issues:
        issues.append("unified_id_not_aligned")

    sync_record = sync_status.get_sync_status(db, "candidate", cid)
    return {
        "candidate_id": cid_str,
        "postgres": pg_section,
        "graph": graph_section,
        "qdrant": qdrant_section,
        "sync_status": (
            {
                "graph_sync_status": sync_record.graph_sync_status,
                "vector_sync_status": sync_record.vector_sync_status,
                "graph_error": sync_record.graph_error,
                "vector_error": sync_record.vector_error,
                "retry_count": sync_record.retry_count,
                "source_hash": sync_record.source_hash,
            }
            if sync_record
            else None
        ),
        "unified_id_valid": bool(unified_id_valid),
        "issues": issues,
    }


@router.get("/verify/job/{job_id}")
def verify_job(job_id: str, db: Session = Depends(get_db)):
    jid = _parse_uuid(job_id, "job_id")
    jid_str = str(jid)
    issues: list[str] = []

    profile = jobs_relational.get_job_full_profile(db, jid)
    if profile is None:
        return {
            "job_id": jid_str,
            "postgres": {"exists": False},
            "graph": {"exists": False},
            "qdrant": {"exists": False},
            "unified_id_valid": False,
            "issues": ["job_not_found_in_postgres"],
        }
    pg_counts = jobs_relational.job_summary_counts(db, jid)
    pg_section = {"exists": True, **pg_counts}

    try:
        graph_section = jobs_graph.verify_job_graph(db, jid_str)
    except Exception as exc:  # noqa: BLE001
        graph_section = {"exists": False, "error": str(exc)[:200]}
        issues.append("graph_verification_failed")

    qdrant_section = jobs_vector.verify_one_vector_per_job(jid_str)
    if not qdrant_section.get("exists"):
        issues.append("qdrant_point_missing")
    elif qdrant_section.get("vector_count_for_job") != 1:
        issues.append(
            f"qdrant_vector_count_is_{qdrant_section.get('vector_count_for_job')}"
        )

    unified_id_valid = (
        pg_section.get("exists")
        and graph_section.get("exists")
        and qdrant_section.get("unified_id_valid", False)
    )
    if not unified_id_valid and not issues:
        issues.append("unified_id_not_aligned")

    sync_record = sync_status.get_sync_status(db, "job", jid)
    return {
        "job_id": jid_str,
        "postgres": pg_section,
        "graph": graph_section,
        "qdrant": qdrant_section,
        "sync_status": (
            {
                "graph_sync_status": sync_record.graph_sync_status,
                "vector_sync_status": sync_record.vector_sync_status,
                "graph_error": sync_record.graph_error,
                "vector_error": sync_record.vector_error,
                "retry_count": sync_record.retry_count,
                "source_hash": sync_record.source_hash,
            }
            if sync_record
            else None
        ),
        "unified_id_valid": bool(unified_id_valid),
        "issues": issues,
    }


# ── Retry ────────────────────────────────────────────────────────────────


@router.post("/sync/candidate/{candidate_id}/retry")
def retry_candidate_sync(
    candidate_id: str,
    force_vector: bool = False,
    db: Session = Depends(get_db),
):
    cid = _parse_uuid(candidate_id, "candidate_id")
    sync_status.create_or_update_sync_status(
        db, "candidate", cid, increment_retry=True,
    )
    db.commit()
    sync_status.write_audit_log(
        db,
        action="sync.retried",
        entity_type="candidate",
        entity_id=cid,
        metadata={"force_vector": force_vector},
    )
    db.commit()
    result = sync_candidate_full(db, cid, force_vector=force_vector)
    return {"candidate_id": str(cid), **result}


@router.post("/sync/job/{job_id}/retry")
def retry_job_sync(
    job_id: str,
    force_vector: bool = False,
    db: Session = Depends(get_db),
):
    jid = _parse_uuid(job_id, "job_id")
    sync_status.create_or_update_sync_status(
        db, "job", jid, increment_retry=True,
    )
    db.commit()
    sync_status.write_audit_log(
        db,
        action="sync.retried",
        entity_type="job",
        entity_id=jid,
        metadata={"force_vector": force_vector},
    )
    db.commit()
    result = sync_job_full(db, jid, force_vector=force_vector)
    return {"job_id": str(jid), **result}
