"""
PATHS Backend — Organization management endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_active_user, require_org_role
from app.db.models.user import User
from app.schemas.organization import CreateMemberRequest, CreateMemberResponse
from app.services import organization_service

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post(
    "/{organization_id}/members",
    response_model=CreateMemberResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_org_role("org_admin"))],
)
def create_organization_member(
    organization_id: UUID,
    data: CreateMemberRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Create a new user assigned to the specified organization.
    Only users with 'org_admin' role in this organization can call this endpoint.
    """
    return organization_service.create_member(db, organization_id, data, current_user)
