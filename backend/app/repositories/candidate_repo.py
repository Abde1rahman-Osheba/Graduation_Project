"""
PATHS Backend — Candidate profile repository.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.candidate import Candidate


class CandidateRepository:
    """Data-access layer for the ``candidates`` table (used as candidate_profiles)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user_id(self, user_id: uuid.UUID) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_profile(
        self,
        *,
        user_id: uuid.UUID,
        full_name: str,
        email: str | None = None,
        phone: str | None = None,
        location: str | None = None,
        headline: str | None = None,
    ) -> Candidate:
        profile = Candidate(
            user_id=user_id,
            full_name=full_name,
            email=email,
            phone=phone,
            location_text=location,
            headline=headline,
        )
        self.db.add(profile)
        self.db.flush()
        return profile
