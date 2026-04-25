"""
Path A + Path B orchestration for organization-side job ↔ candidate matching.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.repositories import organization_matching_repo as om_repo
from app.services.organization_matching import (
    organization_candidate_search_service as search_svc,
    organization_csv_candidate_import_service as csv_svc,
    organization_job_intake_agent as intake,
    organization_ranking_service as rank_svc,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def _disabled() -> bool:
    return not settings.org_matching_enabled


def create_job_request_and_match_from_database(
    db: Session,
    *,
    organization_id: UUID,
    job_request_data: dict[str, Any],
    top_k: int | None = None,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    if _disabled():
        return {"ok": False, "error": "org_matching_disabled"}
    t_k = int(top_k or job_request_data.get("top_k") or settings.org_matching_default_top_k)
    intake_res = intake.normalize_job_intake(
        organization_id, job_request_data.get("job") or job_request_data, top_k=t_k, created_by=created_by,
    )
    job_req, job = intake.persist_job_and_request(
        db, organization_id=organization_id, intake=intake_res,
    )
    run = om_repo.create_matching_run(
        db,
        {
            "organization_id": organization_id,
            "job_request_id": job_req.id,
            "job_id": job.id,
            "path_type": "database_search",
            "top_k": intake_res["top_k"],
        },
    )
    db.commit()

    cands, disc_stats = search_svc.discover_candidates_for_job(db, job.id)
    import asyncio
    r_out = asyncio.run(
        rank_svc.score_candidates_for_job(
            db,
            organization_id=organization_id,
            matching_run_id=run.id,
            job_request_id=job_req.id,
            job_id=job.id,
            candidate_ids=cands,
            top_k=intake_res["top_k"],
        )
    )
    sl = r_out.get("shortlist") or []
    om_repo.finish_matching_run(
        db,
        run.id,
        status="completed",
        totals={
            "total_candidates": disc_stats.get("pg_scanned", 0),
            "relevant_candidates": disc_stats.get("passed_filter", 0),
            "scored_candidates": r_out.get("scored", 0),
            "shortlisted_candidates": len(sl),
            "failed_candidates": r_out.get("failed", 0),
        },
    )
    db.commit()
    return {
        "ok": True,
        "matching_run_id": str(run.id),
        "job_id": str(job.id),
        "job_request_id": str(job_req.id),
        "top_k": intake_res["top_k"],
        "discovery": disc_stats,
        "shortlist": _serialize_shortlist(db, sl),
    }


def create_job_request_and_match_from_csv(
    db: Session,
    *,
    organization_id: UUID,
    job_request_data: dict[str, Any],
    csv_file_bytes: bytes,
    file_name: str,
    top_k: int | None = None,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    if _disabled():
        return {"ok": False, "error": "org_matching_disabled"}
    t_k = int(top_k or job_request_data.get("top_k") or settings.org_matching_default_top_k)
    job_part = job_request_data.get("job") or job_request_data
    intake_res = intake.normalize_job_intake(
        organization_id, job_part, top_k=t_k, created_by=created_by,
    )
    job_req, job = intake.persist_job_and_request(
        db, organization_id=organization_id, intake=intake_res,
    )
    run = om_repo.create_matching_run(
        db,
        {
            "organization_id": organization_id,
            "job_request_id": job_req.id,
            "job_id": job.id,
            "path_type": "csv_candidate_list",
            "top_k": intake_res["top_k"],
        },
    )
    imp = om_repo.create_candidate_import(
        db,
        {
            "organization_id": organization_id,
            "matching_run_id": run.id,
            "file_name": file_name,
        },
    )
    iid = imp.id
    db.commit()

    summary = csv_svc.import_candidates_from_csv(
        db,
        organization_id=organization_id,
        matching_run_id=run.id,
        import_id=iid,
        file_bytes=csv_file_bytes,
        _file_name=file_name,
    )
    om_repo.finish_candidate_import(
        db, iid,
        total_rows=summary.get("total_rows"),
        valid_rows=summary.get("valid_rows"),
        imported_candidates=summary.get("imported_candidates"),
        updated_candidates=summary.get("updated_candidates"),
        failed_rows=summary.get("failed_rows"),
        status="completed",
    )
    db.commit()

    raw_ids = summary.get("candidate_ids") or []
    cand_ids: list[UUID] = []
    for s in raw_ids:
        try:
            cand_ids.append(UUID(s))
        except Exception:  # noqa: BLE001
            pass
    # de-dupe, preserve order
    seen: set[UUID] = set()
    cands: list[UUID] = []
    for c in cand_ids:
        if c not in seen:
            seen.add(c)
            cands.append(c)
    cands = cands[: settings.org_matching_max_candidates_per_run]

    import asyncio
    r_out = asyncio.run(
        rank_svc.score_candidates_for_job(
            db,
            organization_id=organization_id,
            matching_run_id=run.id,
            job_request_id=job_req.id,
            job_id=job.id,
            candidate_ids=cands,
            top_k=intake_res["top_k"],
        )
    )
    sl = r_out.get("shortlist") or []
    om_repo.finish_matching_run(
        db, run.id, status="completed",
        totals={
            "total_candidates": len(cands),
            "relevant_candidates": len(cands),
            "scored_candidates": r_out.get("scored", 0),
            "shortlisted_candidates": len(sl),
            "failed_candidates": r_out.get("failed", 0),
        },
    )
    db.commit()
    return {
        "ok": True,
        "matching_run_id": str(run.id),
        "job_id": str(job.id),
        "job_request_id": str(job_req.id),
        "top_k": intake_res["top_k"],
        "candidate_import": {k: v for k, v in summary.items() if k != "candidate_ids"},
        "shortlist": _serialize_shortlist(db, sl),
    }


def get_matching_run(db: Session, run_id: UUID) -> dict[str, Any] | None:
    r = om_repo.get_matching_run(db, run_id)
    if r is None:
        return None
    return {
        "matching_run_id": str(r.id),
        "organization_id": str(r.organization_id),
        "job_id": str(r.job_id) if r.job_id else None,
        "path_type": r.path_type,
        "top_k": r.top_k,
        "status": r.status,
        "total_candidates": r.total_candidates,
        "relevant_candidates": r.relevant_candidates,
        "scored_candidates": r.scored_candidates,
        "shortlisted_candidates": r.shortlisted_candidates,
        "failed_candidates": r.failed_candidates,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


def get_shortlist(db: Session, run_id: UUID, *, anonymized: bool = True) -> list[dict[str, Any]]:
    return om_repo.get_shortlist(db, run_id, anonymized=anonymized)


def _serialize_shortlist(
    db: Session, rows: list[Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "blind_candidate_id": row.blind_candidate_id,
                "rank_position": row.rank_position,
                "final_score": float(row.final_score),
                "agent_score": float(row.agent_score),
                "vector_similarity_score": float(row.vector_similarity_score),
                "recommendation": row.recommendation,
                "matched_skills": row.matched_skills or [],
                "missing_required_skills": row.missing_required_skills or [],
                "strengths": row.strengths or [],
                "explanation": row.explanation,
            }
        )
    return out
