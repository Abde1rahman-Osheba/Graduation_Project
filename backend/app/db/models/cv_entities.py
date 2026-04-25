"""
PATHS Backend — CV Entities Models.
"""

import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String, Text, Result, select, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

class CandidateDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "candidate_documents"

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="cv")
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_path_or_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)

    candidate = relationship("Candidate")


class Skill(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "skills"

    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)


class CandidateSkill(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "candidate_skills"

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    skill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("skills.id"), nullable=False)
    proficiency_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate = relationship("Candidate")
    skill = relationship("Skill")


class CandidateExperience(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "candidate_experiences"

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate = relationship("Candidate")


class CandidateEducation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "candidate_education"

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    candidate = relationship("Candidate")


class CandidateCertification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "candidate_certifications"

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    expiry_date: Mapped[str | None] = mapped_column(String(50), nullable=True)

    candidate = relationship("Candidate")
