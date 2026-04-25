"""
PATHS Backend — Authentication endpoints.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.db.models.user import User
from app.schemas.auth import (
    CandidateRegisterRequest,
    CandidateRegisterResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    OrganizationRegisterRequest,
    OrganizationRegisterResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register/candidate",
    response_model=CandidateRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_candidate(
    data: CandidateRegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new candidate."""
    return auth_service.register_candidate(db, data)


@router.post(
    "/register/organization",
    response_model=OrganizationRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_organization(
    data: OrganizationRegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new organization and its first administrative user."""
    return auth_service.register_organization(db, data)


@router.post("/login", response_model=LoginResponse)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate and return a JWT access token."""
    return auth_service.login(db, data)


@router.get("/me", response_model=MeResponse)
def get_me(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get the current authenticated user context, including profile and org memberships."""
    return auth_service.get_me_context(db, current_user)
