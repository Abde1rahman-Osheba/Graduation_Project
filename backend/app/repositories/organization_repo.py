"""
PATHS Backend — Organisation repository.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.organization import Organization


class OrganizationRepository:
    """Data-access layer for the ``organizations`` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, org_id) -> Organization | None:
        return self.db.get(Organization, org_id)

    def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_organization(
        self,
        *,
        name: str,
        slug: str,
        industry: str | None = None,
        contact_email: str | None = None,
    ) -> Organization:
        org = Organization(
            name=name,
            slug=slug,
            industry=industry,
            contact_email=contact_email,
            is_active=True,
        )
        self.db.add(org)
        self.db.flush()
        return org
