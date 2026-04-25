"""Request/response models for organization-side matching APIs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class JobPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    summary: str | None = None
    responsibilities: list[str] | None = None
    requirements: list[str] | str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_years_experience: int | None = None
    max_years_experience: int | None = None
    location_text: str | None = None
    workplace_type: str | None = None
    employment_type: str = "full_time"
    seniority_level: str | None = None
    education_requirements: list[str] | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    role_family: str | None = None


class DatabaseSearchRequest(BaseModel):
    organization_id: UUID
    top_k: int = 3
    job: JobPayload


class ApproveOutreachRequest(BaseModel):
    booking_link: str | None = None
    deadline_days: int = 3


class SendOutreachRequest(BaseModel):
    recipient_email: str = Field(..., min_length=3, max_length=320)
