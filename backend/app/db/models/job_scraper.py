"""
PATHS Backend — Job-scraper specific models.

Implements the spec-required tables from
`02_POSTGRES_JOB_IMPORT_REQUIREMENTS.md`:

  * job_skills            (canonical job ↔ skill link with importance)
  * job_requirements      (free-text requirements)
  * job_responsibilities  (free-text responsibilities)
  * job_import_runs       (one row per hourly scheduler run)
  * job_import_errors     (per-record import failures)
  * job_scraper_state     (rolling cursor over the company list)

The existing `jobs`, `companies`, `skills`, and `JobSkillRequirement`
tables remain intact — these are purely additive.
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


class JobSkillLink(Base, UUIDPrimaryKeyMixin):
    """Spec `job_skills` table — links a Job to a canonical Skill row.

    Unlike the legacy `job_skill_requirements` (which stored a denormalised
    skill name string), this table holds a real foreign-key reference
    from `jobs.id` and `skills.id`, plus the requirement type and
    importance score expected by the new graph / vector sync layer.
    """

    __tablename__ = "job_skills"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "skill_id", "requirement_type",
            name="uq_job_skill_requirement",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_type: Mapped[str] = mapped_column(
        String(20), nullable=False,  # "required" or "preferred"
    )
    importance_score: Mapped[float | None] = mapped_column(
        Numeric(6, 3), nullable=True, default=1.0,
    )
    years_required: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class JobRequirementText(Base, UUIDPrimaryKeyMixin):
    """Spec `job_requirements` table — one row per requirement bullet."""

    __tablename__ = "job_requirements"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class JobResponsibility(Base, UUIDPrimaryKeyMixin):
    """Spec `job_responsibilities` table — one row per responsibility bullet."""

    __tablename__ = "job_responsibilities"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    responsibility_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class JobImportRun(Base, UUIDPrimaryKeyMixin):
    """One row per hourly (or manual) job-scraper run."""

    __tablename__ = "job_import_runs"

    source_platform: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    requested_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    scraped_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    graph_synced_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_synced_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="running",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True,
    )


class JobImportError(Base, UUIDPrimaryKeyMixin):
    """Per-record import failure for diagnostics."""

    __tablename__ = "job_import_errors"

    import_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_import_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class JobScraperState(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Rolling cursor that remembers where the last scraper run stopped.

    Each `source_platform` keeps its own offset into the company list so
    the hourly run picks up where the previous one left off and cycles
    through the dataset over time.
    """

    __tablename__ = "job_scraper_state"

    source_platform: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True,
    )
    company_offset: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_imported_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
