"""
PATHS Backend — Authentication schemas (requests & responses).
"""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ── Candidate Registration ────────────────────────────────────────────────

class CandidateRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: str | None = Field(None, max_length=50)
    location: str | None = Field(None, max_length=255)
    headline: str | None = Field(None, max_length=500)


class CandidateRegisterResponse(BaseModel):
    user_id: UUID
    candidate_profile_id: UUID
    account_type: str
    message: str


# ── Organisation Registration ─────────────────────────────────────────────

class OrganizationRegisterRequest(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=255)
    organization_slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    industry: str | None = Field(None, max_length=255)
    organization_email: EmailStr | None = None
    first_admin_full_name: str = Field(..., min_length=1, max_length=255)
    first_admin_email: EmailStr
    first_admin_password: str = Field(..., min_length=8, max_length=128)


class OrganizationRegisterResponse(BaseModel):
    organization_id: UUID
    user_id: UUID
    role_code: str
    message: str


# ── Login ─────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OrganizationContext(BaseModel):
    organization_id: UUID
    organization_name: str
    role_code: str


class UserSummary(BaseModel):
    id: UUID
    email: str
    full_name: str
    account_type: str
    organization: OrganizationContext | None = None

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSummary


# ── /auth/me ──────────────────────────────────────────────────────────────

class CandidateProfileSummary(BaseModel):
    id: UUID
    phone: str | None = None
    location: str | None = None
    headline: str | None = None

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    account_type: str
    is_active: bool
    candidate_profile: CandidateProfileSummary | None = None
    organization: OrganizationContext | None = None

    model_config = {"from_attributes": True}
