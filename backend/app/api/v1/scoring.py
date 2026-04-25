"""
PATHS Backend — Candidate-Job scoring API endpoints.

All routes live under ``/api/v1/scoring``. They are thin wrappers
around `ScoringService` — every business rule (relevance filtering,
prompt anonymization, OpenRouter call, vector similarity, sync to AGE)
lives in `app/services/scoring/`.

Routes:
  POST /api/v1/scoring/candidates/{candidate_id}/score
  GET  /api/v1/scoring/candidates/{candidate_id}/scores
  GET  /api/v1/scoring/candidates/{candidate_id}/jobs/{job_id}
  POST /api/v1/scoring/candidates/{candidate_id}/jobs/{job_id}/score
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.models.job import Job
from app.db.models.scoring import CandidateJobScore
from app.db.repositories import scoring_repository as repo
from app.schemas.scoring import (
    CandidateScoreDetail,
    CandidateScoreItem,
    CandidateScoreListResponse,
    ScoreCandidateAgainstJobRequest,
    ScoreCandidateRequest,
    ScoreCandidateResponse,
    TopMatchOut,
)
from app.services.scoring.scoring_service import ScoringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scoring", tags=["Scoring"])


def _parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field} UUID",
        ) from exc


def _resolve_job_metadata(db: Session, job_id: UUID) -> tuple[str | None, str | None]:
    """Return (title, company_name) for use in score list responses."""
    job = db.get(Job, job_id)
    if job is None:
        return None, None
    return job.title, job.company_name


def _score_to_item(db: Session, score: CandidateJobScore) -> CandidateScoreItem:
    title, company = _resolve_job_metadata(db, score.job_id)
    return CandidateScoreItem(
        job_id=str(score.job_id),
        job_title=title,
        company_name=company,
        agent_score=float(score.agent_score),
        vector_similarity_score=float(score.vector_similarity_score),
        final_score=float(score.final_score),
        relevance_score=float(score.relevance_score) if score.relevance_score is not None else None,
        role_family=score.role_family,
        recommendation=score.recommendation,
        match_classification=score.match_classification,
        confidence=float(score.confidence) if score.confidence is not None else None,
        scoring_status=score.scoring_status,
        model_name=score.model_name,
        prompt_version=score.prompt_version,
        scoring_date=score.updated_at or score.created_at,
    )


def _score_to_detail(db: Session, score: CandidateJobScore) -> CandidateScoreDetail:
    base = _score_to_item(db, score).model_dump()
    return CandidateScoreDetail(
        candidate_id=str(score.candidate_id),
        **base,
        criteria_breakdown=score.criteria_breakdown,
        matched_skills=list(score.matched_skills or []),
        missing_required_skills=list(score.missing_required_skills or []),
        missing_preferred_skills=list(score.missing_preferred_skills or []),
        strengths=list(score.strengths or []),
        weaknesses=list(score.weaknesses or []),
        explanation=score.explanation,
    )


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post(
    "/candidates/{candidate_id}/score",
    response_model=ScoreCandidateResponse,
    summary="Score a candidate against the most relevant active jobs.",
)
async def score_candidate(
    candidate_id: str,
    body: ScoreCandidateRequest = Body(default_factory=ScoreCandidateRequest),
):
    cid = _parse_uuid(candidate_id, "candidate_id")
    service = ScoringService()
    try:
        result = await service.score_candidate(
            cid,
            max_jobs=body.max_jobs,
            force_rescore=body.force_rescore,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("scoring run crashed for candidate %s", cid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"scoring_failed: {exc}",
        ) from exc

    if result.status == "failed" and "candidate_not_found" in result.errors:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    return ScoreCandidateResponse(
        candidate_id=result.candidate_id,
        scoring_run_id=result.scoring_run_id,
        candidate_role_family=result.candidate_role_family,
        total_relevant_jobs=result.total_relevant_jobs,
        scored_jobs=result.scored_jobs,
        skipped_jobs=result.skipped_jobs,
        failed_jobs=result.failed_jobs,
        status=result.status,
        started_at=result.started_at,
        finished_at=result.finished_at,
        top_matches=[
            TopMatchOut(
                job_id=m.job_id,
                job_title=m.job_title,
                company_name=m.company_name,
                agent_score=m.agent_score,
                vector_similarity_score=m.vector_similarity_score,
                final_score=m.final_score,
                recommendation=m.recommendation,
                match_classification=m.match_classification,
            )
            for m in result.top_matches
        ],
        errors=result.errors,
    )


@router.get(
    "/candidates/{candidate_id}/scores",
    response_model=CandidateScoreListResponse,
    summary="List saved candidate-job scores ordered by final_score DESC.",
)
def get_candidate_scores(
    candidate_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    cid = _parse_uuid(candidate_id, "candidate_id")
    rows = repo.get_candidate_scores(db, cid, limit=limit)
    items = [_score_to_item(db, r) for r in rows]
    return CandidateScoreListResponse(candidate_id=str(cid), items=items)


@router.get(
    "/candidates/{candidate_id}/jobs/{job_id}",
    response_model=CandidateScoreDetail,
    summary="Get the full scoring detail for one (candidate, job) pair.",
)
def get_score_detail(
    candidate_id: str,
    job_id: str,
    db: Session = Depends(get_db),
):
    cid = _parse_uuid(candidate_id, "candidate_id")
    jid = _parse_uuid(job_id, "job_id")
    score = repo.get_candidate_score_detail(db, cid, jid)
    if score is None:
        raise HTTPException(status_code=404, detail="score_not_found")
    return _score_to_detail(db, score)


@router.post(
    "/candidates/{candidate_id}/jobs/{job_id}/score",
    response_model=CandidateScoreDetail,
    summary="Score a candidate against one specific job (recruiter / admin).",
)
async def score_candidate_against_job(
    candidate_id: str,
    job_id: str,
    body: ScoreCandidateAgainstJobRequest = Body(
        default_factory=ScoreCandidateAgainstJobRequest,
    ),
    db: Session = Depends(get_db),
):
    cid = _parse_uuid(candidate_id, "candidate_id")
    jid = _parse_uuid(job_id, "job_id")
    service = ScoringService()
    try:
        score = await service.score_candidate_against_job(
            cid, jid, force=body.force,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("single-job scoring crashed for %s/%s", cid, jid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"scoring_failed: {exc}",
        ) from exc

    if score is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="score_not_produced (job may be irrelevant — pass force=true)",
        )
    # Re-fetch with this session so relationships are fresh
    score = (
        db.execute(
            select(CandidateJobScore).where(CandidateJobScore.id == score.id)
        ).scalar_one()
    )
    return _score_to_detail(db, score)
