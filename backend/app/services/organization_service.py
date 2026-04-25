"""
PATHS Backend — Organisation service.

Handles member management operations scoped to an organisation.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.role_repo import RoleRepository
from app.repositories.user_repo import UserRepository
from app.schemas.organization import CreateMemberRequest, CreateMemberResponse


def create_member(
    db: Session,
    organization_id: uuid.UUID,
    data: CreateMemberRequest,
    current_user: User,
) -> CreateMemberResponse:
    """Create a new organisation member.  Only callable by org_admin."""
    user_repo = UserRepository(db)
    org_repo = OrganizationRepository(db)
    role_repo = RoleRepository(db)

    # Ensure org exists
    org = org_repo.get_by_id(organization_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    # Email uniqueness
    if user_repo.get_by_email(data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    new_user = user_repo.create_user(
        email=data.email,
        full_name=data.full_name,
        plain_password=data.password,
        account_type="organization_member",
    )

    membership = role_repo.create_membership(
        user_id=new_user.id,
        organization_id=organization_id,
        role_code=data.role_code,
    )

    db.commit()
    db.refresh(new_user)
    db.refresh(membership)

    return CreateMemberResponse(
        member_id=membership.id,
        user_id=new_user.id,
        organization_id=organization_id,
        role_code=membership.role_code,
    )
