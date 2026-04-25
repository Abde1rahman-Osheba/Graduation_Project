"""
PATHS Backend — Role / membership repository.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.application import OrganizationMember


ALLOWED_ROLES = {"recruiter", "hr", "hr_manager", "hiring_manager", "org_admin"}


class RoleRepository:
    """Data-access layer for the ``organization_members`` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_membership(
        self,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        role_code: str,
    ) -> OrganizationMember:
        if role_code not in ALLOWED_ROLES:
            raise ValueError(f"Invalid role_code '{role_code}'. Must be one of {ALLOWED_ROLES}")

        member = OrganizationMember(
            user_id=user_id,
            organization_id=organization_id,
            role_code=role_code,
            is_active=True,
        )
        self.db.add(member)
        self.db.flush()
        return member

    def get_membership(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> OrganizationMember | None:
        stmt = select(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == organization_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_memberships(
        self, user_id: uuid.UUID
    ) -> list[OrganizationMember]:
        stmt = select(OrganizationMember).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
        return list(self.db.execute(stmt).scalars().all())
