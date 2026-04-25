"""
PATHS Backend — Job Ingestion models.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, Float, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def utc_now():
    return datetime.now(timezone.utc)

class JobSourceRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "job_source_runs"

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")
    
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    error_summary_jsonb: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True, default="system")
    
    raw_items = relationship("JobRawItem", back_populates="source_run", cascade="all, delete-orphan")
    errors = relationship("IngestionError", back_populates="source_run", cascade="all, delete-orphan")


class JobRawItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "job_raw_items"

    source_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_source_runs.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    raw_payload_jsonb: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fetch_status: Mapped[str] = mapped_column(String(50), nullable=False, default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    source_run = relationship("JobSourceRun", back_populates="raw_items")


class JobSkillRequirement(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "job_skill_requirements"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    skill_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_name_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    importance_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extracted_by: Mapped[str] = mapped_column(String(50), nullable=False, default="rule")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    

class IngestionError(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ingestion_errors"

    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_source_runs.id"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    stage: Mapped[str] = mapped_column(String(50), nullable=False) # fetch / parse / normalize / dedupe / persist / project
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    details_jsonb: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    source_run = relationship("JobSourceRun", back_populates="errors")


class JobVectorProjectionStatus(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "job_vector_projection_status"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    vector_backend: Mapped[str] = mapped_column(String(50), nullable=False, default="qdrant")
    collection_name: Mapped[str] = mapped_column(String(100), nullable=False)
    point_id: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    projection_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
