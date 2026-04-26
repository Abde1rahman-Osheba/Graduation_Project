from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DecisionSupportGenerateRequest(BaseModel):
    candidate_id: UUID
    job_id: UUID
    application_id: UUID


class HrDecisionRequest(BaseModel):
    final_decision: str = Field(
        ...,
        description="accepted | rejected | hold | another_hr_interview | another_technical_interview | manager_review",
    )
    hr_notes: str | None = None
    override_reason: str | None = None


class EmailPatchRequest(BaseModel):
    subject: str | None = None
    body: str | None = None
