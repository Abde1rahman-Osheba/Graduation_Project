"""
PATHS Backend — User repository.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models.user import User


class UserRepository:
    """Data-access layer for the ``users`` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_user(
        self,
        *,
        email: str,
        full_name: str,
        plain_password: str,
        account_type: str = "candidate",
    ) -> User:
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(plain_password),
            account_type=account_type,
            is_active=True,
        )
        self.db.add(user)
        self.db.flush()  # get id without committing (caller owns the transaction)
        return user
