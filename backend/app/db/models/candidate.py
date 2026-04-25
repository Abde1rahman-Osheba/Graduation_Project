"""
PATHS Backend — Candidate model.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Candidate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "candidates"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, unique=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    # Relationships
    user = relationship("User", back_populates="candidate_profile", lazy="selectin")
    applications = relationship("Application", back_populates="candidate", lazy="selectin")
