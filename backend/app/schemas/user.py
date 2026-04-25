"""
PATHS Backend — User schemas.
"""

from uuid import UUID

from pydantic import BaseModel


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    account_type: str
    is_active: bool

    model_config = {"from_attributes": True}
