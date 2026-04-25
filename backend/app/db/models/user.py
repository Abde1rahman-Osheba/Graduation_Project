"""
PATHS Backend — User model.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="candidate",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    memberships = relationship("OrganizationMember", back_populates="user", lazy="selectin")
    candidate_profile = relationship("Candidate", back_populates="user", uselist=False, lazy="selectin")
