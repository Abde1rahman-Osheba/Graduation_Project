"""
PATHS Backend — Normalized reference entities (companies, locations).

These tables back the spec-compliant relational schema described in
`02_RELATIONAL_POSTGRES_SCHEMA_REQUIREMENTS.md`. They are additive: the
existing legacy columns (e.g. `candidates.location_text`,
`jobs.company_name`) remain and continue to work. New code can resolve to
normalized rows where useful.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Company(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Normalized company / employer entity."""

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True,
    )
    website_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Location(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Normalized location entity (geographic / remote)."""

    __tablename__ = "locations"

    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    remote_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,  # onsite, hybrid, remote
    )
