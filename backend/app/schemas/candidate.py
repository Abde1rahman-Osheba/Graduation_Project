"""
PATHS Backend — Candidate profile schemas.
"""

from uuid import UUID

from pydantic import BaseModel


class CandidateProfileOut(BaseModel):
    id: UUID
    phone: str | None = None
    location: str | None = None
    headline: str | None = None

    model_config = {"from_attributes": True}
