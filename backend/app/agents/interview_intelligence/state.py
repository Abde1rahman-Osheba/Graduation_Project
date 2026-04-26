"""Shared LangGraph / pipeline state for interview post-processing."""

from __future__ import annotations

from typing import Any, TypedDict


class InterviewGraphState(TypedDict, total=False):
    interview_id: str
    organization_id: str
    error: str

    # Loaded context (serializable dicts)
    job_context: dict[str, Any]
    candidate_context: dict[str, Any]
    application_context: dict[str, Any]
    question_packs: list[dict[str, Any]]
    transcript: str
    transcript_quality: str
    job_match_score: float | None

    # Agent outputs
    interview_summary: dict[str, Any]
    hr_scorecard: dict[str, Any]
    technical_scorecard: dict[str, Any]
    compliance: dict[str, Any]
    decision_packet: dict[str, Any]
