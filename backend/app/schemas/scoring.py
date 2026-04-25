"""
PATHS Backend — Pydantic schemas for the candidate-job scoring API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request bodies ───────────────────────────────────────────────────────


class ScoreCandidateRequest(BaseModel):
    max_jobs: int | None = Field(default=None, ge=1, le=100)
    force_rescore: bool = False


class ScoreCandidateAgainstJobRequest(BaseModel):
    force: bool = False


# ── Response objects ─────────────────────────────────────────────────────


class TopMatchOut(BaseModel):
    job_id: str
    job_title: str
    company_name: str | None = None
    agent_score: float
    vector_similarity_score: float
    final_score: float
    recommendation: str
    match_classification: str | None = None


class ScoreCandidateResponse(BaseModel):
    candidate_id: str
    scoring_run_id: str | None = None
    candidate_role_family: str
    total_relevant_jobs: int
    scored_jobs: int
    skipped_jobs: int
    failed_jobs: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    top_matches: list[TopMatchOut] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CandidateScoreItem(BaseModel):
    job_id: str
    job_title: str | None = None
    company_name: str | None = None
    agent_score: float
    vector_similarity_score: float
    final_score: float
    relevance_score: float | None = None
    role_family: str | None = None
    recommendation: str | None = None
    match_classification: str | None = None
    confidence: float | None = None
    scoring_status: str
    model_name: str | None = None
    prompt_version: str
    scoring_date: datetime | None = None


class CandidateScoreListResponse(BaseModel):
    candidate_id: str
    items: list[CandidateScoreItem]


class CandidateScoreDetail(CandidateScoreItem):
    candidate_id: str
    criteria_breakdown: dict[str, Any] | None = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    explanation: str | None = None


__all__ = [
    "ScoreCandidateRequest",
    "ScoreCandidateAgainstJobRequest",
    "TopMatchOut",
    "ScoreCandidateResponse",
    "CandidateScoreItem",
    "CandidateScoreListResponse",
    "CandidateScoreDetail",
]
