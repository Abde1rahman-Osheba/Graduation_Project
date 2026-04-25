"""
PATHS Backend — FastAPI authentication and authorization dependencies.

Provides reusable Depends-compatible helpers:
  - get_current_user           — extract + validate JWT
  - get_current_active_user    — ensure is_active flag
  - require_account_type(...)  — gate by account type
  - require_org_role(...)      — gate by organisation role
"""

from typing import Sequence
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.db.models.user import User
from app.db.models.application import OrganizationMember

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── Core user extraction ──────────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode bearer token and return the corresponding User row."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    email: str | None = payload.get("sub")
    if email is None:
        raise credentials_exception

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


# ── Account-type gate ─────────────────────────────────────────────────────

def require_account_type(*allowed_types: str):
    """Return a dependency that rejects users whose account_type is not in *allowed_types*."""

    def _dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.account_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account type '{current_user.account_type}' is not permitted for this resource",
            )
        return current_user

    return _dependency


# ── Organisation role gate ────────────────────────────────────────────────

def require_org_role(*allowed_roles: str):
    """Return a dependency that rejects users who are not members of the
    target organisation (path param ``organization_id``) with one of the
    *allowed_roles*.

    The path **must** contain ``{organization_id}`` as a UUID path parameter.
    """

    def _dependency(
        organization_id: UUID,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.account_type != "organization_member":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization members can access this resource",
            )
        membership = db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == current_user.id,
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()

        if membership is None or membership.role_code not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles {list(allowed_roles)} in this organisation",
            )
        return current_user

    return _dependency
