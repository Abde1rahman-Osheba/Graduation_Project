"""
PATHS Backend — Organization-side matching, anonymization & outreach models.

Implements the 7 spec-required tables from
`PATHS_Organization_Candidate_Search_Outreach_Cursor_Instructions.md` §11:

  * organization_job_requests
  * organization_matching_runs
  * organization_candidate_imports
  * organization_candidate_import_errors
  * organization_blind_candidate_maps
  * organization_candidate_rankings
  * organization_outreach_messages

These are additive — none of the existing tables are renamed or dropped.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class OrganizationJobRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Raw job request submitted by an organization."""

    __tablename__ = "organization_job_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    requirements: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    required_skills: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    preferred_skills: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    education_requirements: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    min_years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seniority_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workplace_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

    role_family: Mapped[str | None] = mapped_column(String(80), nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual",
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="created",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )


class OrganizationMatchingRun(Base, UUIDPrimaryKeyMixin):
    """One row per matching pipeline execution."""

    __tablename__ = "organization_matching_runs"
    __table_args__ = (
        CheckConstraint(
            "path_type IN ('database_search', 'csv_candidate_list')",
            name="ck_org_matching_run_path_type",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    job_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_job_requests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    path_type: Mapped[str] = mapped_column(String(50), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    total_candidates: Mapped[int] = mapped_column(Integer, default=0)
    relevant_candidates: Mapped[int] = mapped_column(Integer, default=0)
    scored_candidates: Mapped[int] = mapped_column(Integer, default=0)
    shortlisted_candidates: Mapped[int] = mapped_column(Integer, default=0)
    failed_candidates: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="running",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class OrganizationCandidateImport(Base, UUIDPrimaryKeyMixin):
    """Per-CSV import-job summary."""

    __tablename__ = "organization_candidate_imports"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    matching_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_matching_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported_candidates: Mapped[int] = mapped_column(Integer, default=0)
    updated_candidates: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="running",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class OrganizationCandidateImportError(Base, UUIDPrimaryKeyMixin):
    """Per-row failure inside a CSV import."""

    __tablename__ = "organization_candidate_import_errors"

    import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_candidate_imports.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    matching_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_matching_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cv_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class OrganizationBlindCandidateMap(Base, UUIDPrimaryKeyMixin):
    """Maps real candidate IDs to blind ones for a specific matching run."""

    __tablename__ = "organization_blind_candidate_maps"
    __table_args__ = (
        UniqueConstraint(
            "matching_run_id", "candidate_id",
            name="uq_org_blind_run_candidate",
        ),
        UniqueConstraint(
            "matching_run_id", "blind_candidate_id",
            name="uq_org_blind_run_blind_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    matching_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_matching_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    blind_candidate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    de_anonymized: Mapped[bool] = mapped_column(Boolean, default=False)
    de_anonymized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    de_anonymized_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    de_anonymization_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class OrganizationCandidateRanking(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-candidate ranking row for one matching run."""

    __tablename__ = "organization_candidate_rankings"
    __table_args__ = (
        UniqueConstraint(
            "matching_run_id", "candidate_id",
            name="uq_org_ranking_run_candidate",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    matching_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_matching_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_job_requests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    blind_candidate_id: Mapped[str] = mapped_column(String(80), nullable=False)

    rank_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    vector_similarity_score: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False,
    )
    final_score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(
        Numeric(6, 3), nullable=True,
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
    match_classification: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ranked",
    )


class OrganizationOutreachMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Generated outreach email tied to a candidate ranking."""

    __tablename__ = "organization_outreach_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    matching_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_matching_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ranking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization_candidate_rankings.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    blind_candidate_id: Mapped[str] = mapped_column(String(80), nullable=False)

    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    booking_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft",
    )
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
