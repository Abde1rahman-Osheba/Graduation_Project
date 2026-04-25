"""
PATHS — Organization-side matching, rankings, and outreach (PostgreSQL).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.db.models.candidate import Candidate
from app.db.models.job import Job
from app.db.models.organization import Organization
from app.db.models.organization_matching import (
    OrganizationBlindCandidateMap,
    OrganizationCandidateImport,
    OrganizationCandidateImportError,
    OrganizationCandidateRanking,
    OrganizationJobRequest,
    OrganizationMatchingRun,
    OrganizationOutreachMessage,
)

# ── Job request ─────────────────────────────────────────────────────────


def create_job_request(db: Session, data: dict[str, Any]) -> OrganizationJobRequest:
    row = OrganizationJobRequest(
        organization_id=data["organization_id"],
        job_id=data.get("job_id"),
        title=data.get("title") or "Untitled",
        summary=data.get("summary"),
        description=data.get("description"),
        responsibilities=data.get("responsibilities"),
        requirements=data.get("requirements"),
        required_skills=data.get("required_skills"),
        preferred_skills=data.get("preferred_skills"),
        education_requirements=data.get("education_requirements"),
        min_years_experience=data.get("min_years_experience"),
        max_years_experience=data.get("max_years_experience"),
        seniority_level=data.get("seniority_level"),
        location_text=data.get("location_text"),
        workplace_type=data.get("workplace_type"),
        employment_type=data.get("employment_type"),
        salary_min=data.get("salary_min"),
        salary_max=data.get("salary_max"),
        salary_currency=data.get("salary_currency"),
        role_family=data.get("role_family"),
        top_k=int(data.get("top_k", 3)),
        source_type=data.get("source_type", "manual"),
        status=data.get("status", "created"),
        created_by=data.get("created_by"),
    )
    db.add(row)
    db.flush()
    return row


def update_job_request(
    db: Session, request_id: UUID, **fields: Any,
) -> OrganizationJobRequest | None:
    row = db.get(OrganizationJobRequest, request_id)
    if row is None:
        return None
    for k, v in fields.items():
        if hasattr(row, k) and v is not None:
            setattr(row, k, v)
    db.flush()
    return row


# ── Matching run ─────────────────────────────────────────────────────


def create_matching_run(db: Session, data: dict[str, Any]) -> OrganizationMatchingRun:
    row = OrganizationMatchingRun(
        organization_id=data["organization_id"],
        job_request_id=data.get("job_request_id"),
        job_id=data.get("job_id"),
        path_type=data["path_type"],
        top_k=int(data.get("top_k", 3)),
        status=data.get("status", "running"),
        run_metadata=data.get("metadata") or data.get("run_metadata"),
    )
    db.add(row)
    db.flush()
    return row


def get_matching_run(db: Session, run_id: UUID) -> OrganizationMatchingRun | None:
    return db.get(OrganizationMatchingRun, run_id)


def finish_matching_run(
    db: Session,
    run_id: UUID,
    *,
    status: str,
    totals: dict[str, int] | None = None,
    error_message: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> OrganizationMatchingRun | None:
    run = db.get(OrganizationMatchingRun, run_id)
    if run is None:
        return None
    run.status = status
    run.finished_at = datetime.now(timezone.utc)
    if error_message is not None:
        run.error_message = error_message[:2000]
    t = totals or {}
    for key in (
        "total_candidates", "relevant_candidates", "scored_candidates",
        "shortlisted_candidates", "failed_candidates",
    ):
        if key in t:
            setattr(run, key, int(t[key]))
    if extra_metadata:
        run.run_metadata = {**(run.run_metadata or {}), **extra_metadata}
    db.flush()
    return run


# ── CSV import ───────────────────────────────────────────────────────


def create_candidate_import(
    db: Session, data: dict[str, Any],
) -> OrganizationCandidateImport:
    row = OrganizationCandidateImport(
        organization_id=data["organization_id"],
        matching_run_id=data["matching_run_id"],
        file_name=data.get("file_name"),
        status=data.get("status", "running"),
        import_metadata=data.get("metadata") or data.get("import_metadata"),
    )
    db.add(row)
    db.flush()
    return row


def finish_candidate_import(
    db: Session, import_id: UUID, **counts: int | str | None,
) -> None:
    imp = db.get(OrganizationCandidateImport, import_id)
    if imp is None:
        return
    for k, v in counts.items():
        if hasattr(imp, k) and v is not None and k != "status":
            setattr(imp, k, v)
    if counts.get("status"):
        imp.status = str(counts["status"])
    imp.finished_at = datetime.now(timezone.utc)
    db.flush()


def log_candidate_import_error(
    db: Session, data: dict[str, Any],
) -> None:
    row = OrganizationCandidateImportError(
        import_id=data.get("import_id"),
        matching_run_id=data.get("matching_run_id"),
        row_number=data.get("row_number"),
        cv_url=data.get("cv_url"),
        error_type=data.get("error_type"),
        error_message=(data.get("error_message") or "")[:2000],
        raw_row=data.get("raw_row"),
    )
    db.add(row)
    db.flush()


# ── Blind map ─────────────────────────────────────────────────────────


def _next_blind_index(db: Session, matching_run_id: UUID) -> int:
    n = db.execute(
        select(OrganizationBlindCandidateMap).where(
            OrganizationBlindCandidateMap.matching_run_id == matching_run_id
        )
    ).scalars().all()
    return len(n) + 1


def create_blind_candidate_map(
    db: Session,
    *,
    organization_id: UUID,
    matching_run_id: UUID,
    candidate_id: UUID,
) -> str:
    existing = db.execute(
        select(OrganizationBlindCandidateMap).where(
            and_(
                OrganizationBlindCandidateMap.matching_run_id == matching_run_id,
                OrganizationBlindCandidateMap.candidate_id == candidate_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing.blind_candidate_id

    idx = _next_blind_index(db, matching_run_id)
    year = datetime.now(timezone.utc).year
    run_short = str(matching_run_id).replace("-", "")[:6].upper()
    blind = f"ORG-RUN-{year}-{run_short}-CAND-{idx:04d}"
    row = OrganizationBlindCandidateMap(
        organization_id=organization_id,
        matching_run_id=matching_run_id,
        candidate_id=candidate_id,
        blind_candidate_id=blind,
    )
    db.add(row)
    db.flush()
    return blind


def get_blind_candidate_map(
    db: Session, matching_run_id: UUID, candidate_id: UUID,
) -> OrganizationBlindCandidateMap | None:
    return db.execute(
        select(OrganizationBlindCandidateMap).where(
            and_(
                OrganizationBlindCandidateMap.matching_run_id == matching_run_id,
                OrganizationBlindCandidateMap.candidate_id == candidate_id,
            )
        )
    ).scalar_one_or_none()


def get_blind_by_blind_id(
    db: Session, matching_run_id: UUID, blind_candidate_id: str,
) -> OrganizationBlindCandidateMap | None:
    return db.execute(
        select(OrganizationBlindCandidateMap).where(
            and_(
                OrganizationBlindCandidateMap.matching_run_id == matching_run_id,
                OrganizationBlindCandidateMap.blind_candidate_id == blind_candidate_id,
            )
        )
    ).scalar_one_or_none()


# ── Rankings ───────────────────────────────────────────────────────────


def upsert_candidate_ranking(db: Session, data: dict[str, Any]) -> OrganizationCandidateRanking:
    existing = db.execute(
        select(OrganizationCandidateRanking).where(
            and_(
                OrganizationCandidateRanking.matching_run_id == data["matching_run_id"],
                OrganizationCandidateRanking.candidate_id == data["candidate_id"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        for k, v in data.items():
            if hasattr(existing, k) and v is not None:
                setattr(existing, k, v)
        db.flush()
        return existing
    row = OrganizationCandidateRanking(
        organization_id=data["organization_id"],
        matching_run_id=data["matching_run_id"],
        job_request_id=data.get("job_request_id"),
        job_id=data.get("job_id"),
        candidate_id=data["candidate_id"],
        blind_candidate_id=data["blind_candidate_id"],
        rank_position=data.get("rank_position"),
        agent_score=data["agent_score"],
        vector_similarity_score=data["vector_similarity_score"],
        final_score=data["final_score"],
        relevance_score=data.get("relevance_score"),
        criteria_breakdown=data.get("criteria_breakdown"),
        matched_skills=data.get("matched_skills"),
        missing_required_skills=data.get("missing_required_skills"),
        missing_preferred_skills=data.get("missing_preferred_skills"),
        strengths=data.get("strengths"),
        weaknesses=data.get("weaknesses"),
        explanation=data.get("explanation"),
        recommendation=data.get("recommendation"),
        match_classification=data.get("match_classification"),
        status=data.get("status", "ranked"),
    )
    db.add(row)
    db.flush()
    return row


def get_ranking(db: Session, ranking_id: UUID) -> OrganizationCandidateRanking | None:
    return db.get(OrganizationCandidateRanking, ranking_id)


def get_shortlist(
    db: Session, run_id: UUID, *, anonymized: bool = True,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(OrganizationCandidateRanking)
        .where(OrganizationCandidateRanking.matching_run_id == run_id)
        .order_by(desc(OrganizationCandidateRanking.final_score))
    ).scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        item: dict[str, Any] = {
            "ranking_id": str(r.id),
            "blind_candidate_id": r.blind_candidate_id,
            "rank_position": r.rank_position,
            "agent_score": float(r.agent_score),
            "vector_similarity_score": float(r.vector_similarity_score),
            "final_score": float(r.final_score),
            "recommendation": r.recommendation,
            "matched_skills": r.matched_skills or [],
            "missing_required_skills": r.missing_required_skills or [],
            "missing_preferred_skills": r.missing_preferred_skills or [],
            "strengths": r.strengths or [],
            "weaknesses": r.weaknesses or [],
            "explanation": r.explanation,
            "status": r.status,
        }
        if not anonymized:
            item["candidate_id"] = str(r.candidate_id)
        out.append(item)
    return out


# ── Outreach ─────────────────────────────────────────────────────────


def create_outreach_message(db: Session, data: dict[str, Any]) -> OrganizationOutreachMessage:
    row = OrganizationOutreachMessage(
        organization_id=data["organization_id"],
        matching_run_id=data["matching_run_id"],
        ranking_id=data.get("ranking_id"),
        job_id=data.get("job_id"),
        candidate_id=data.get("candidate_id"),
        blind_candidate_id=data["blind_candidate_id"],
        recipient_email=data.get("recipient_email"),
        subject=data["subject"],
        body=data["body"],
        booking_link=data.get("booking_link"),
        reply_deadline_at=data.get("reply_deadline_at"),
        status=data.get("status", "draft"),
    )
    db.add(row)
    db.flush()
    return row


def update_outreach_message_status(
    db: Session,
    message_id: UUID,
    *,
    status: str,
    **extra: Any,
) -> OrganizationOutreachMessage | None:
    m = db.get(OrganizationOutreachMessage, message_id)
    if m is None:
        return None
    m.status = status
    if "error_message" in extra and extra["error_message"] is not None:
        m.error_message = str(extra["error_message"])[:2000]
    if "provider" in extra:
        m.provider = extra.get("provider")
    if "provider_message_id" in extra:
        m.provider_message_id = extra.get("provider_message_id")
    if "approved_by" in extra:
        m.approved_by = extra.get("approved_by")
    if "approved_at" in extra and extra["approved_at"] is not None:
        m.approved_at = extra["approved_at"]
    if "sent_at" in extra and extra["sent_at"] is not None:
        m.sent_at = extra["sent_at"]
    if "subject" in extra and extra["subject"] is not None:
        m.subject = extra["subject"][:500]
    if "body" in extra and extra["body"] is not None:
        m.body = extra["body"]
    db.flush()
    return m


def get_outreach_message(db: Session, message_id: UUID) -> OrganizationOutreachMessage | None:
    return db.get(OrganizationOutreachMessage, message_id)


# ── Lookups for orchestrator ───────────────────────────────────────────


def get_job_request(db: Session, request_id: UUID) -> OrganizationJobRequest | None:
    return db.get(OrganizationJobRequest, request_id)


def get_org_profile(db: Session, org_id: UUID) -> dict[str, Any] | None:
    o = db.get(Organization, org_id)
    if o is None:
        return None
    return {"id": str(o.id), "name": o.name, "slug": o.slug, "industry": o.industry}


def get_job_title(db: Session, job_id: UUID) -> str | None:
    j = db.get(Job, job_id)
    return j.title if j else None


def get_candidate_email(db: Session, candidate_id: UUID) -> str | None:
    c = db.get(Candidate, candidate_id)
    return c.email if c else None
