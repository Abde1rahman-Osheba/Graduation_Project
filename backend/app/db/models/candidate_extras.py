"""
PATHS Backend — Additional candidate-related entities for the unified
database integration spec.

Adds projects, contacts, and links as separate spec-compliant tables.
Existing `candidate_documents`, `candidate_skills`, `candidate_experiences`,
`candidate_education`, `candidate_certifications` are intentionally left
untouched.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CandidateContact(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Stores individual contact channels for a candidate."""

    __tablename__ = "candidate_contacts"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_type: Mapped[str] = mapped_column(
        String(50), nullable=False,  # email, phone, linkedin, github, portfolio, website
    )
    contact_value: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)


class CandidateProject(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Project entries extracted from CVs / portfolios."""

    __tablename__ = "candidate_projects"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    technologies: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True,
    )
    start_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)


class CandidateLink(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """External profile / portfolio links for a candidate."""

    __tablename__ = "candidate_links"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
