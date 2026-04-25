"""
PATHS Backend — Candidate-Job scoring models.

Implements the spec-required tables from the
`PATHS_Candidate_Job_Scoring_Service_Cursor_Instructions.md`:

  * candidate_job_scores  — saved match between a candidate and a job
  * scoring_runs          — one row per scoring execution
  * scoring_errors        — per-job failures captured during a run

The existing `candidate_job_matches` table (general-purpose multi-score
record) is intentionally left in place — it has a different schema and
serves a different purpose (free-form evidence/version), so the spec's
`candidate_job_scores` table is added alongside it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CandidateJobScore(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Spec `candidate_job_scores` table.

    One row per `(candidate_id, job_id)`. Holds both the
    LLM-generated `agent_score`, the Qdrant `vector_similarity_score`,
    and the combined `final_score`, plus the structured criteria
    breakdown returned by the agent.
    """

    __tablename__ = "candidate_job_scores"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "job_id", name="uq_candidate_job_score",
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    agent_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    vector_similarity_score: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False,
    )
    final_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)

    relevance_score: Mapped[float | None] = mapped_column(
        Numeric(6, 3), nullable=True,
    )
    role_family: Mapped[str | None] = mapped_column(String(80), nullable=True)
    match_classification: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )

    criteria_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    matched_skills: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    missing_required_skills: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
    )
    missing_preferred_skills: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
    )
    strengths: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    weaknesses: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="v1",
    )
    scoring_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="completed",
    )


class ScoringRun(Base, UUIDPrimaryKeyMixin):
    """One row per `score_candidate(...)` invocation."""

    __tablename__ = "scoring_runs"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    total_relevant_jobs: Mapped[int] = mapped_column(Integer, default=0)
    scored_jobs: Mapped[int] = mapped_column(Integer, default=0)
    skipped_jobs: Mapped[int] = mapped_column(Integer, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="running",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True,
    )


class ScoringError(Base, UUIDPrimaryKeyMixin):
    """Per-job failure captured during a scoring run."""

    __tablename__ = "scoring_errors"

    scoring_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scoring_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class ScoringCriteriaConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Optional configurable scoring criteria (used when an admin overrides
    the default 6-criteria layout). Reads default from `scoring_criteria.py`
    when this table is empty.
    """

    __tablename__ = "scoring_criteria"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
