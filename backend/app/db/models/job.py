"""
PATHS Backend — Job model.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, Float, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Job(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "jobs"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True,
    )
    
    # Ingestion specific fields
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True, default="manual")
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    # Spec-compliant generic source fields used by the hourly Job_Scraper-main
    # integration (`source_platform` / `source_external_id`). Existing
    # source_type / source_name are kept for the legacy job_ingestion flow.
    source_platform: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    source_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True,
    )
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    title_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    role_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="full_time")
    seniority_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Numeric experience range (per scraper spec)
    min_years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Workplace type (remote/hybrid/onsite/unknown) — separate from
    # the legacy `location_mode` column so existing rows aren't disturbed.
    workplace_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="remote")
    
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    ingestion_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="active")

    # Per-job sync state used by the spec checklist (06_*).  These mirror
    # the rows in `db_sync_status` but live on the job itself for fast
    # filtering ("WHERE graph_sync_status='failed'").
    graph_sync_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="pending",
    )
    vector_sync_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="pending",
    )
    last_graph_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_vector_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    text_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    raw_payload_jsonb: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="jobs", lazy="selectin")
    applications = relationship("Application", back_populates="job", lazy="selectin")
