"""
PATHS Backend — Candidate relational repository (PostgreSQL).

Implements the spec-required functions from
`02_RELATIONAL_POSTGRES_SCHEMA_REQUIREMENTS.md`. PostgreSQL is the canonical
source of truth — every candidate row created here owns the canonical
`candidate_id` UUID that is then propagated to Apache AGE and Qdrant.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.candidate import Candidate
from app.db.models.candidate_extras import (
    CandidateContact,
    CandidateLink,
    CandidateProject,
)
from app.db.models.cv_entities import (
    CandidateCertification,
    CandidateDocument,
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    Skill,
)
from app.db.models.reference import Company, Location


# ── Result containers ────────────────────────────────────────────────────


@dataclass
class CandidateFullProfile:
    """Aggregated read model used by graph + vector sync."""

    candidate: Candidate
    skills: list[tuple[CandidateSkill, Skill]] = field(default_factory=list)
    experiences: list[tuple[CandidateExperience, Company | None]] = field(
        default_factory=list,
    )
    education: list[CandidateEducation] = field(default_factory=list)
    projects: list[CandidateProject] = field(default_factory=list)
    certifications: list[CandidateCertification] = field(default_factory=list)
    contacts: list[CandidateContact] = field(default_factory=list)
    links: list[CandidateLink] = field(default_factory=list)
    documents: list[CandidateDocument] = field(default_factory=list)
    location: Location | None = None
    current_company: Company | None = None


# ── Helpers: skills, companies, locations ────────────────────────────────


def _normalize(name: str | None) -> str:
    if not name:
        return ""
    return name.strip().lower()


def get_or_create_skill(
    db: Session,
    name: str,
    *,
    category: str | None = None,
) -> Skill:
    """Return the canonical Skill row for `name`, creating it if missing."""
    normalized = _normalize(name)
    if not normalized:
        raise ValueError("skill name is required")

    existing = db.execute(
        select(Skill).where(Skill.normalized_name == normalized)
    ).scalar_one_or_none()
    if existing:
        if category and not existing.category:
            existing.category = category
            db.flush()
        return existing

    skill = Skill(normalized_name=normalized, category=category)
    db.add(skill)
    db.flush()
    return skill


def get_or_create_company(db: Session, name: str, **extra: Any) -> Company:
    normalized = _normalize(name)
    if not normalized:
        raise ValueError("company name is required")

    existing = db.execute(
        select(Company).where(Company.normalized_name == normalized)
    ).scalar_one_or_none()
    if existing:
        return existing

    company = Company(name=name.strip(), normalized_name=normalized, **extra)
    db.add(company)
    db.flush()
    return company


def get_or_create_location(db: Session, **data: Any) -> Location | None:
    """Find or create a normalized Location row from country/city/region."""
    country = (data.get("country") or "").strip() or None
    city = (data.get("city") or "").strip() or None
    region = (data.get("region") or "").strip() or None
    remote_type = (data.get("remote_type") or "").strip() or None

    if not any([country, city, region, remote_type]):
        return None

    stmt = select(Location).where(
        Location.country.is_(country) if country is None else Location.country == country,
        Location.city.is_(city) if city is None else Location.city == city,
        Location.region.is_(region) if region is None else Location.region == region,
        Location.remote_type.is_(remote_type)
        if remote_type is None
        else Location.remote_type == remote_type,
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        return existing

    loc = Location(country=country, city=city, region=region, remote_type=remote_type)
    db.add(loc)
    db.flush()
    return loc


# ── Candidate CRUD ───────────────────────────────────────────────────────


def create_candidate(db: Session, data: dict[str, Any]) -> Candidate:
    """Create a candidate row. The caller may pre-supply an id (UUID)."""
    candidate_id = data.get("id") or uuid.uuid4()
    if isinstance(candidate_id, str):
        candidate_id = UUID(candidate_id)

    candidate = Candidate(
        id=candidate_id,
        full_name=data.get("full_name") or "Unknown",
        email=data.get("email"),
        phone=data.get("phone"),
        current_title=data.get("current_title"),
        location_text=data.get("location_text"),
        headline=data.get("headline"),
        years_experience=data.get("years_experience"),
        summary=data.get("summary"),
        status=data.get("status") or "active",
    )
    db.add(candidate)
    db.flush()
    return candidate


def update_candidate(
    db: Session, candidate_id: UUID | str, data: dict[str, Any],
) -> Candidate:
    cid = UUID(str(candidate_id))
    candidate = db.get(Candidate, cid)
    if candidate is None:
        raise LookupError(f"Candidate {cid} not found")

    for field_name in (
        "full_name",
        "email",
        "phone",
        "current_title",
        "location_text",
        "headline",
        "years_experience",
        "summary",
        "status",
    ):
        if field_name in data and data[field_name] is not None:
            setattr(candidate, field_name, data[field_name])
    db.flush()
    return candidate


def get_candidate(db: Session, candidate_id: UUID | str) -> Candidate | None:
    return db.get(Candidate, UUID(str(candidate_id)))


def list_active_candidate_ids(
    db: Session, *, limit: int = 10000,
) -> list[UUID]:
    """Return candidate primary keys for active profiles (pool for org Path A)."""
    rows = db.execute(
        select(Candidate.id)
        .where(Candidate.status == "active")
        .order_by(desc(Candidate.updated_at), Candidate.id)
        .limit(limit)
    ).scalars().all()
    return [r for r in rows if r is not None]


def get_candidate_full_profile(
    db: Session, candidate_id: UUID | str,
) -> CandidateFullProfile | None:
    """Load the candidate plus all related rows used by sync."""
    cid = UUID(str(candidate_id))
    candidate = db.get(Candidate, cid)
    if candidate is None:
        return None

    profile = CandidateFullProfile(candidate=candidate)

    skill_rows = db.execute(
        select(CandidateSkill, Skill)
        .join(Skill, CandidateSkill.skill_id == Skill.id)
        .where(CandidateSkill.candidate_id == cid)
    ).all()
    profile.skills = [(cs, sk) for cs, sk in skill_rows]

    exps = db.execute(
        select(CandidateExperience).where(CandidateExperience.candidate_id == cid)
    ).scalars().all()
    company_lookup: dict[str, Company] = {}
    for exp in exps:
        company = None
        if exp.company_name:
            normalized = _normalize(exp.company_name)
            if normalized in company_lookup:
                company = company_lookup[normalized]
            else:
                company = db.execute(
                    select(Company).where(Company.normalized_name == normalized)
                ).scalar_one_or_none()
                if company:
                    company_lookup[normalized] = company
        profile.experiences.append((exp, company))

    profile.education = list(
        db.execute(
            select(CandidateEducation).where(CandidateEducation.candidate_id == cid)
        ).scalars().all()
    )
    profile.projects = list(
        db.execute(
            select(CandidateProject).where(CandidateProject.candidate_id == cid)
        ).scalars().all()
    )
    profile.certifications = list(
        db.execute(
            select(CandidateCertification).where(
                CandidateCertification.candidate_id == cid
            )
        ).scalars().all()
    )
    profile.contacts = list(
        db.execute(
            select(CandidateContact).where(CandidateContact.candidate_id == cid)
        ).scalars().all()
    )
    profile.links = list(
        db.execute(
            select(CandidateLink).where(CandidateLink.candidate_id == cid)
        ).scalars().all()
    )
    profile.documents = list(
        db.execute(
            select(CandidateDocument).where(CandidateDocument.candidate_id == cid)
        ).scalars().all()
    )
    return profile


# ── Skill / experience upsert ────────────────────────────────────────────


def upsert_candidate_skill(
    db: Session,
    candidate_id: UUID | str,
    skill_data: dict[str, Any],
) -> CandidateSkill:
    cid = UUID(str(candidate_id))
    skill_name = skill_data.get("name") or skill_data.get("normalized_name")
    if not skill_name:
        raise ValueError("skill name required")
    skill = get_or_create_skill(
        db, skill_name, category=skill_data.get("category"),
    )

    link = db.execute(
        select(CandidateSkill).where(
            CandidateSkill.candidate_id == cid,
            CandidateSkill.skill_id == skill.id,
        )
    ).scalar_one_or_none()
    if link is None:
        link = CandidateSkill(candidate_id=cid, skill_id=skill.id)
        db.add(link)

    if "proficiency_score" in skill_data:
        link.proficiency_score = skill_data["proficiency_score"]
    if "years_used" in skill_data:
        link.years_used = skill_data["years_used"]
    if "evidence_text" in skill_data or "evidence" in skill_data:
        link.evidence_text = skill_data.get("evidence_text") or skill_data.get("evidence")
    db.flush()
    return link


def upsert_candidate_experience(
    db: Session,
    candidate_id: UUID | str,
    experience_data: dict[str, Any],
) -> CandidateExperience:
    cid = UUID(str(candidate_id))
    company_name = experience_data.get("company_name") or "Unknown"
    title = experience_data.get("title") or "Unknown Role"

    existing = db.execute(
        select(CandidateExperience).where(
            CandidateExperience.candidate_id == cid,
            CandidateExperience.company_name == company_name,
            CandidateExperience.title == title,
            CandidateExperience.start_date == experience_data.get("start_date"),
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = CandidateExperience(
            candidate_id=cid,
            company_name=company_name,
            title=title,
            start_date=experience_data.get("start_date"),
            end_date=experience_data.get("end_date"),
            description=experience_data.get("description"),
        )
        db.add(existing)
    else:
        if experience_data.get("end_date"):
            existing.end_date = experience_data["end_date"]
        if experience_data.get("description"):
            existing.description = experience_data["description"]

    if company_name and company_name != "Unknown":
        get_or_create_company(db, company_name)

    db.flush()
    return existing


# ── Contacts / links / projects helpers ──────────────────────────────────


def upsert_candidate_contact(
    db: Session,
    candidate_id: UUID | str,
    *,
    contact_type: str,
    contact_value: str,
    is_primary: bool = False,
    source: str | None = None,
    confidence: float | None = None,
) -> CandidateContact | None:
    if not contact_type or not contact_value:
        return None
    cid = UUID(str(candidate_id))
    existing = db.execute(
        select(CandidateContact).where(
            CandidateContact.candidate_id == cid,
            CandidateContact.contact_type == contact_type,
            CandidateContact.contact_value == contact_value,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    contact = CandidateContact(
        candidate_id=cid,
        contact_type=contact_type,
        contact_value=contact_value,
        is_primary=is_primary,
        source=source,
        confidence=confidence,
    )
    db.add(contact)
    db.flush()
    return contact


def upsert_candidate_link(
    db: Session,
    candidate_id: UUID | str,
    *,
    link_type: str,
    url: str,
    label: str | None = None,
) -> CandidateLink | None:
    if not url:
        return None
    cid = UUID(str(candidate_id))
    existing = db.execute(
        select(CandidateLink).where(
            CandidateLink.candidate_id == cid, CandidateLink.url == url,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    link = CandidateLink(
        candidate_id=cid, link_type=link_type, url=url, label=label,
    )
    db.add(link)
    db.flush()
    return link


def upsert_candidate_project(
    db: Session,
    candidate_id: UUID | str,
    project_data: dict[str, Any],
) -> CandidateProject | None:
    name = (project_data.get("name") or "").strip()
    if not name:
        return None
    cid = UUID(str(candidate_id))
    existing = db.execute(
        select(CandidateProject).where(
            CandidateProject.candidate_id == cid, CandidateProject.name == name,
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = CandidateProject(candidate_id=cid, name=name)
        db.add(existing)
    for f in (
        "description",
        "project_url",
        "repository_url",
        "technologies",
        "start_date",
        "end_date",
        "source",
        "confidence",
    ):
        if f in project_data and project_data[f] is not None:
            setattr(existing, f, project_data[f])
    db.flush()
    return existing


# ── Counts (used by verify endpoint) ─────────────────────────────────────


def candidate_summary_counts(
    db: Session, candidate_id: UUID | str,
) -> dict[str, int | bool]:
    cid = UUID(str(candidate_id))
    skills_count = db.execute(
        select(CandidateSkill).where(CandidateSkill.candidate_id == cid)
    ).all()
    exp_count = db.execute(
        select(CandidateExperience).where(CandidateExperience.candidate_id == cid)
    ).all()
    edu_count = db.execute(
        select(CandidateEducation).where(CandidateEducation.candidate_id == cid)
    ).all()
    cert_count = db.execute(
        select(CandidateCertification).where(CandidateCertification.candidate_id == cid)
    ).all()
    docs = list(
        db.execute(
            select(CandidateDocument).where(CandidateDocument.candidate_id == cid)
        ).scalars().all()
    )
    return {
        "skills_count": len(skills_count),
        "experiences_count": len(exp_count),
        "education_count": len(edu_count),
        "certifications_count": len(cert_count),
        "documents_count": len(docs),
        "sanitized_cv_exists": any((d.raw_text or "").strip() for d in docs),
    }
