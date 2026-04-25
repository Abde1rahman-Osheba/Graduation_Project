"""
PATHS Backend — Organisation schemas.
"""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class OrganizationOut(BaseModel):
    id: UUID
    name: str
    slug: str
    industry: str | None = None
    contact_email: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class CreateMemberRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role_code: str = Field(..., pattern=r"^(recruiter|hr|hr_manager|hiring_manager|org_admin)$")


class CreateMemberResponse(BaseModel):
    member_id: UUID
    user_id: UUID
    organization_id: UUID
    role_code: str
