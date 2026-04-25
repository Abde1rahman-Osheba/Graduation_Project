"""
PATHS Backend — Synchronization, audit, and matching tables.

Implements the spec-required `db_sync_status`, `audit_logs`, and
`candidate_job_matches` tables defined in
`02_RELATIONAL_POSTGRES_SCHEMA_REQUIREMENTS.md`.
"""

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


class DBSyncStatus(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks AGE / Qdrant sync state for an entity row in PostgreSQL."""

    __tablename__ = "db_sync_status"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_db_sync_entity"),
    )

    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,  # candidate, job, skill, company
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
    )
    graph_sync_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",  # pending, success, failed
    )
    vector_sync_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",
    )
    graph_last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    vector_last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    graph_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    vector_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Append-only audit trail for important entity actions."""

    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    audit_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class CandidateJobMatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Stores AI-generated match scores between a candidate and a job."""

    __tablename__ = "candidate_job_matches"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "job_id", "model_version",
            name="uq_match_candidate_job_model",
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False, index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, index=True,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True,
    )
    overall_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    skill_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    experience_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    education_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    semantic_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    graph_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    fairness_adjusted_score: Mapped[float | None] = mapped_column(
        Numeric(6, 3), nullable=True,
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
