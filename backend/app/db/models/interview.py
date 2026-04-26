"""
PATHS — Interview intelligence schema (HR + technical workflow, HITL decisions).

Tables back scheduling, question packs, transcripts, summaries, evaluations,
decision packets, and human decisions. Auditing uses the shared `audit_logs` table.
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


class Interview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "interviews"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    interview_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="mixed",
    )  # hr | technical | mixed
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft",
    )
    # draft | scheduled | rescheduled | cancelled | completed | no_show

    scheduled_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    scheduled_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    meeting_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # google_meet | zoom | teams | manual
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    calendar_event_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_calendar_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    # Relationships
    application = relationship("Application", lazy="selectin")
    participants = relationship(
        "InterviewParticipant",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    question_packs = relationship(
        "InterviewQuestionPack",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    transcripts = relationship(
        "InterviewTranscript",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    summaries = relationship(
        "InterviewSummary",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    evaluations = relationship(
        "InterviewEvaluation",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    decision_packets = relationship(
        "InterviewDecisionPacket",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    human_decisions = relationship(
        "InterviewHumanDecision",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class InterviewParticipant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "interview_participants"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    role: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )  # hr | technical_interviewer | hiring_manager | candidate
    attendance_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
    )  # invited | confirmed | attended | absent

    interview = relationship("Interview", back_populates="participants")


class InterviewQuestionPack(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "interview_question_packs"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_pack_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )  # hr | technical | mixed
    generated_by_agent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    questions_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    approved_by_hr: Mapped[bool] = mapped_column(default=False, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    interview = relationship("Interview", back_populates="question_packs")


class InterviewTranscript(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "interview_transcripts"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    transcript_source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="uploaded_text",
    )
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quality_hint: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
    )  # high | medium | low
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    interview = relationship("Interview", back_populates="transcripts")


class InterviewSummary(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "interview_summaries"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_by_agent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    interview = relationship("Interview", back_populates="summaries")


class InterviewEvaluation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "interview_evaluations"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )  # hr | technical | final
    score_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    strengths_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    weaknesses_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    interview = relationship("Interview", back_populates="evaluations")


class InterviewDecisionPacket(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "interview_decision_packets"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    recommendation: Mapped[str | None] = mapped_column(String(80), nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_packet_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(
        default=True, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    interview = relationship("Interview", back_populates="decision_packets")


class InterviewHumanDecision(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "interview_human_decisions"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decided_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False,
    )
    final_decision: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )  # accepted | rejected | hold | another_interview
    hr_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    interview = relationship("Interview", back_populates="human_decisions")
