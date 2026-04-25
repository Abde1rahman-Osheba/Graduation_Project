"""
PATHS Backend — Authentication service.

Orchestrates candidate registration, organisation onboarding, login,
and the /me context builder.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.repositories.candidate_repo import CandidateRepository
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.role_repo import RoleRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    CandidateRegisterRequest,
    CandidateRegisterResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    OrganizationContext,
    OrganizationRegisterRequest,
    OrganizationRegisterResponse,
    UserSummary,
    CandidateProfileSummary,
)


# ── Candidate Registration ────────────────────────────────────────────────

def register_candidate(db: Session, data: CandidateRegisterRequest) -> CandidateRegisterResponse:
    user_repo = UserRepository(db)
    cand_repo = CandidateRepository(db)

    # uniqueness check
    if user_repo.get_by_email(data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = user_repo.create_user(
        email=data.email,
        full_name=data.full_name,
        plain_password=data.password,
        account_type="candidate",
    )

    profile = cand_repo.create_profile(
        user_id=user.id,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        location=data.location,
        headline=data.headline,
    )

    db.commit()
    db.refresh(user)
    db.refresh(profile)

    return CandidateRegisterResponse(
        user_id=user.id,
        candidate_profile_id=profile.id,
        account_type=user.account_type,
        message="Candidate registered successfully",
    )


# ── Organisation Registration ─────────────────────────────────────────────

def register_organization(
    db: Session, data: OrganizationRegisterRequest
) -> OrganizationRegisterResponse:
    user_repo = UserRepository(db)
    org_repo = OrganizationRepository(db)
    role_repo = RoleRepository(db)

    # uniqueness checks
    if org_repo.get_by_slug(data.organization_slug):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organisation with this slug already exists",
        )
    if user_repo.get_by_email(data.first_admin_email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with the admin email already exists",
        )

    org = org_repo.create_organization(
        name=data.organization_name,
        slug=data.organization_slug,
        industry=data.industry,
        contact_email=data.organization_email,
    )

    admin_user = user_repo.create_user(
        email=data.first_admin_email,
        full_name=data.first_admin_full_name,
        plain_password=data.first_admin_password,
        account_type="organization_member",
    )

    role_repo.create_membership(
        user_id=admin_user.id,
        organization_id=org.id,
        role_code="org_admin",
    )

    db.commit()
    db.refresh(org)
    db.refresh(admin_user)

    return OrganizationRegisterResponse(
        organization_id=org.id,
        user_id=admin_user.id,
        role_code="org_admin",
        message="Organisation registered successfully",
    )


# ── Login ─────────────────────────────────────────────────────────────────

def login(db: Session, data: LoginRequest) -> LoginResponse:
    user_repo = UserRepository(db)
    role_repo = RoleRepository(db)

    user = user_repo.get_by_email(data.email)

    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Build JWT claims
    claims: dict = {"sub": user.email, "account_type": user.account_type}
    org_context: OrganizationContext | None = None

    if user.account_type == "organization_member":
        memberships = role_repo.get_user_memberships(user.id)
        if memberships:
            m = memberships[0]  # primary membership
            claims["organization_id"] = str(m.organization_id)
            claims["role_code"] = m.role_code
            org_context = OrganizationContext(
                organization_id=m.organization_id,
                organization_name=m.organization.name,
                role_code=m.role_code,
            )

    token = create_access_token(claims)

    return LoginResponse(
        access_token=token,
        user=UserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            account_type=user.account_type,
            organization=org_context,
        ),
    )


# ── /auth/me Context Builder ─────────────────────────────────────────────

def get_me_context(db: Session, user) -> MeResponse:
    """Build the full user context for GET /auth/me."""
    role_repo = RoleRepository(db)

    candidate_profile: CandidateProfileSummary | None = None
    org_context: OrganizationContext | None = None

    if user.account_type == "candidate" and user.candidate_profile:
        p = user.candidate_profile
        candidate_profile = CandidateProfileSummary(
            id=p.id,
            phone=p.phone,
            location=p.location_text,
            headline=p.headline,
        )

    if user.account_type == "organization_member":
        memberships = role_repo.get_user_memberships(user.id)
        if memberships:
            m = memberships[0]
            org_context = OrganizationContext(
                organization_id=m.organization_id,
                organization_name=m.organization.name,
                role_code=m.role_code,
            )

    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        account_type=user.account_type,
        is_active=user.is_active,
        candidate_profile=candidate_profile,
        organization=org_context,
    )
