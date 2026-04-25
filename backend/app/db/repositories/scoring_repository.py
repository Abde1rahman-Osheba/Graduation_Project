"""
PATHS Backend — Scoring repository.

Implements the spec-required helpers from
`PATHS_Candidate_Job_Scoring_Service_Cursor_Instructions.md` §15:

  * create_scoring_run / finish_scoring_run
  * get_candidate_profile / get_relevant_jobs / get_job_profile
  * upsert_candidate_job_score / get_candidate_scores / get_candidate_score_detail
  * log_scoring_error
  * get_existing_score (used when force_rescore=False)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.job import Job
from app.db.models.scoring import (
    CandidateJobScore,
    ScoringError,
    ScoringRun,
)
from app.db.repositories.candidates_relational import (
    CandidateFullProfile,
    get_candidate_full_profile,
)
from app.db.repositories.jobs_relational import (
    JobFullProfile,
    get_job_full_profile,
)

logger = logging.getLogger(__name__)


# ── Scoring-run lifecycle ───────────────────────────────────────────────


def create_scoring_run(
    db: Session, candidate_id: UUID, *, metadata: dict[str, Any] | None = None,
) -> ScoringRun:
    run = ScoringRun(
        candidate_id=candidate_id,
        status="running",
        run_metadata=metadata,
    )
    db.add(run)
    db.flush()
    return run


def finish_scoring_run(
    db: Session,
    run: ScoringRun,
    *,
    status: str,
    counts: dict[str, int],
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ScoringRun:
    run.finished_at = datetime.now(timezone.utc)
    run.status = status
    run.total_relevant_jobs = counts.get("total_relevant_jobs", 0)
    run.scored_jobs = counts.get("scored_jobs", 0)
    run.skipped_jobs = counts.get("skipped_jobs", 0)
    run.failed_jobs = counts.get("failed_jobs", 0)
    if error_message is not None:
        run.error_message = error_message[:2000]
    if metadata is not None:
        run.run_metadata = {**(run.run_metadata or {}), **metadata}
    db.flush()
    return run


# ── Profile + job listing helpers ───────────────────────────────────────


def get_candidate_profile(
    db: Session, candidate_id: UUID,
) -> CandidateFullProfile | None:
    return get_candidate_full_profile(db, candidate_id)


def get_job_profile(db: Session, job_id: UUID) -> JobFullProfile | None:
    return get_job_full_profile(db, job_id)


def get_active_jobs(
    db: Session, *, limit: int = 200,
) -> list[Job]:
    """Return currently active jobs the scoring service can choose from.

    Ordered by `last_imported_at` desc so newer scraper imports take
    priority. The relevance filter is applied later in the orchestrator.
    """
    return list(
        db.execute(
            select(Job)
            .where(
                Job.is_active == True,  # noqa: E712
                Job.status.in_(["active", "open", "draft"]),
            )
            .order_by(
                desc(Job.last_imported_at).nullslast(),
                desc(Job.created_at),
            )
            .limit(max(1, int(limit)))
        ).scalars().all()
    )


# ── Score upsert + lookup ───────────────────────────────────────────────


def get_existing_score(
    db: Session, candidate_id: UUID, job_id: UUID,
) -> CandidateJobScore | None:
    return db.execute(
        select(CandidateJobScore).where(
            CandidateJobScore.candidate_id == candidate_id,
            CandidateJobScore.job_id == job_id,
        )
    ).scalar_one_or_none()


def upsert_candidate_job_score(
    db: Session, score_data: dict[str, Any],
) -> CandidateJobScore:
    """Insert or update a CandidateJobScore row (PK on (candidate_id, job_id))."""
    candidate_id = score_data["candidate_id"]
    job_id = score_data["job_id"]
    existing = get_existing_score(db, candidate_id, job_id)
    if existing is None:
        score = CandidateJobScore(**score_data)
        db.add(score)
        db.flush()
        return score

    for field_name, value in score_data.items():
        if field_name in {"id", "created_at"}:
            continue
        setattr(existing, field_name, value)
    db.flush()
    return existing


def get_candidate_scores(
    db: Session, candidate_id: UUID, *, limit: int = 100,
) -> list[CandidateJobScore]:
    return list(
        db.execute(
            select(CandidateJobScore)
            .where(CandidateJobScore.candidate_id == candidate_id)
            .order_by(desc(CandidateJobScore.final_score))
            .limit(max(1, int(limit)))
        ).scalars().all()
    )


def get_candidate_score_detail(
    db: Session, candidate_id: UUID, job_id: UUID,
) -> CandidateJobScore | None:
    return get_existing_score(db, candidate_id, job_id)


# ── Error logging ───────────────────────────────────────────────────────


def log_scoring_error(
    db: Session,
    *,
    scoring_run_id: UUID | None,
    candidate_id: UUID | None,
    job_id: UUID | None,
    error_type: str,
    error_message: str,
    metadata: dict[str, Any] | None = None,
) -> ScoringError:
    err = ScoringError(
        scoring_run_id=scoring_run_id,
        candidate_id=candidate_id,
        job_id=job_id,
        error_type=error_type[:100] if error_type else None,
        error_message=(error_message or "")[:2000],
        error_metadata=metadata,
    )
    db.add(err)
    db.flush()
    return err


def list_recent_runs(
    db: Session, candidate_id: UUID, *, limit: int = 5,
) -> list[ScoringRun]:
    return list(
        db.execute(
            select(ScoringRun)
            .where(ScoringRun.candidate_id == candidate_id)
            .order_by(desc(ScoringRun.started_at))
            .limit(max(1, int(limit)))
        ).scalars().all()
    )


__all__ = [
    "create_scoring_run",
    "finish_scoring_run",
    "get_candidate_profile",
    "get_job_profile",
    "get_active_jobs",
    "get_existing_score",
    "upsert_candidate_job_score",
    "get_candidate_scores",
    "get_candidate_score_detail",
    "log_scoring_error",
    "list_recent_runs",
]
