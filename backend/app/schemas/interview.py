"""
Pydantic schemas for the interview intelligence module (API contracts).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Availability / scheduling ──────────────────────────────────────────


class TimeSlotOut(BaseModel):
    start: datetime
    end: datetime
    timezone: str = "UTC"


class InterviewAvailabilityRequest(BaseModel):
    organization_id: UUID
    job_id: UUID | None = None
    interviewer_user_ids: list[UUID] = Field(default_factory=list)
    from_date: datetime | None = None
    to_date: datetime | None = None
    slot_minutes: int = 30


class InterviewAvailabilityResponse(BaseModel):
    organization_id: UUID
    slots: list[TimeSlotOut]


class InterviewScheduleRequest(BaseModel):
    application_id: UUID
    organization_id: UUID
    interview_type: str = Field(
        "mixed", description="hr | technical | mixed",
    )
    slot_start: datetime
    slot_end: datetime
    timezone: str = "UTC"
    participant_user_ids: list[UUID] = Field(default_factory=list)
    meeting_provider: str | None = Field(
        None, description="google_meet | zoom | teams | manual",
    )
    manual_meeting_url: str | None = None
    create_calendar_event: bool = True


class InterviewScheduleResponse(BaseModel):
    interview_id: UUID
    status: str
    meeting_url: str | None
    meeting_provider: str | None
    calendar_event_id: str | None
    message: str | None = None


class InterviewRescheduleRequest(BaseModel):
    new_start: datetime
    new_end: datetime
    timezone: str = "UTC"


class InterviewCancelRequest(BaseModel):
    reason: str | None = None


# ── Question packs ────────────────────────────────────────────────────


class GenerateInterviewQuestionsRequest(BaseModel):
    include_hr: bool = True
    include_technical: bool = True
    regenerate: bool = False


class ApproveInterviewQuestionsRequest(BaseModel):
    approved: bool = True
    edited_questions_json: dict[str, Any] | None = None


class InterviewQuestionPackOut(BaseModel):
    id: UUID
    question_pack_type: str
    questions_json: dict[str, Any]
    approved_by_hr: bool
    approved_at: datetime | None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


# ── Transcript ────────────────────────────────────────────────────────


class InterviewTranscriptCreate(BaseModel):
    transcript_text: str
    transcript_source: str = "uploaded_text"
    language: str | None = "en"
    quality_hint: str | None = None  # high | medium | low


# ── Analysis & decisions ──────────────────────────────────────────────


class InterviewSummaryOut(BaseModel):
    id: UUID
    summary_json: dict[str, Any]
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class InterviewEvaluationOut(BaseModel):
    id: UUID
    evaluation_type: str
    score_json: dict[str, Any]
    recommendation: str | None
    confidence: float | None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class InterviewDecisionPacketOut(BaseModel):
    id: UUID
    recommendation: str | None
    final_score: float | None
    confidence: float | None
    decision_packet_json: dict[str, Any]
    human_review_required: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class InterviewAnalyzeResponse(BaseModel):
    interview_id: UUID
    summary: InterviewSummaryOut | None
    hr_evaluation: InterviewEvaluationOut | None
    technical_evaluation: InterviewEvaluationOut | None
    decision_packet: InterviewDecisionPacketOut | None
    compliance: dict[str, Any]
    message: str | None = None


class InterviewHumanDecisionRequest(BaseModel):
    final_decision: str = Field(
        ...,
        description="accepted | rejected | hold | another_interview",
    )
    hr_notes: str | None = None
    override_reason: str | None = None
    ai_recommendation_acknowledged: bool = True


class InterviewHumanDecisionOut(BaseModel):
    id: UUID
    final_decision: str
    hr_notes: str | None
    override_reason: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class InterviewCreateStub(BaseModel):
    """When frontend creates an interview before scheduling."""

    application_id: UUID
    organization_id: UUID
    interview_type: str = "mixed"
