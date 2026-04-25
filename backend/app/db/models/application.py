"""
PATHS Backend — Application, OrganizationMember, and AuditEvent models.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Application(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "applications"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False,
    )
    application_type: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    source_channel: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_stage_code: Mapped[str] = mapped_column(String(50), nullable=False, default="applied")
    overall_status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    # Relationships
    candidate = relationship("Candidate", back_populates="applications", lazy="selectin")
    job = relationship("Job", back_populates="applications", lazy="selectin")


class OrganizationMember(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_member_user_org"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    role_code: Mapped[str] = mapped_column(String(50), nullable=False, default="member")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # Relationships
    organization = relationship("Organization", back_populates="members", lazy="selectin")
    user = relationship("User", back_populates="memberships", lazy="selectin")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    before_jsonb: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_jsonb: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
