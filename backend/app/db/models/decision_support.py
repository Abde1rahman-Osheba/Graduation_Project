"""
PATHS — End-to-end Decision Support System (DSS) tables.

AI recommends; HR records final decisions. Auditing uses `audit_logs`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DecisionSupportPacket(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "decision_support_packets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    generated_by_agent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    final_journey_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    packet_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    compliance_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # pass|warning|fail
    human_review_required: Mapped[bool] = mapped_column(default=True, nullable=False)

    score_breakdowns = relationship(
        "DecisionScoreBreakdown", back_populates="packet", cascade="all, delete-orphan",
    )
    hr_decisions = relationship(
        "HrFinalDecision", back_populates="packet", cascade="all, delete-orphan",
    )
    development_plans = relationship(
        "DevelopmentPlan", back_populates="packet", cascade="all, delete-orphan",
    )
    decision_emails = relationship(
        "DecisionEmail", back_populates="packet", cascade="all, delete-orphan",
    )


class DecisionScoreBreakdown(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "decision_score_breakdowns"

    decision_packet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_support_packets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_job_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    assessment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    technical_interview_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_interview_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_alignment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_journey_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scoring_formula_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    explanation_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    packet = relationship("DecisionSupportPacket", back_populates="score_breakdowns")


class HrFinalDecision(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "hr_final_decisions"

    decision_packet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_support_packets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False,
    )
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False,
    )
    ai_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_hr_decision: Mapped[str] = mapped_column(String(64), nullable=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hr_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    packet = relationship("DecisionSupportPacket", back_populates="hr_decisions")


class DevelopmentPlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "development_plans"

    decision_packet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_support_packets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False,
    )
    plan_type: Mapped[str] = mapped_column(
        String(64), nullable=False,
    )  # accepted_internal_growth | rejected_improvement_plan
    generated_by_agent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    packet = relationship("DecisionSupportPacket", back_populates="development_plans")


class DecisionEmail(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "decision_emails"

    decision_packet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_support_packets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    email_type: Mapped[str] = mapped_column(String(32), nullable=False)  # acceptance | rejection
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by_agent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft",
    )  # draft | approved | sent | failed
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    packet = relationship("DecisionSupportPacket", back_populates="decision_emails")
