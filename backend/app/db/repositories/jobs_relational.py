"""
PATHS Backend — Job relational repository (PostgreSQL).

Implements spec-required job-side functions: `create_job`, `update_job`,
`get_job`, `get_job_full_profile`, and `upsert_job_required_skill`.

Backwards compatible with the existing `JobIngestionRepository` — the
canonical Job row is the same.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.cv_entities import Skill
from app.db.models.job import Job
from app.db.models.job_ingestion import JobSkillRequirement
from app.db.models.organization import Organization
from app.db.models.reference import Company, Location
from app.db.repositories.candidates_relational import (
    _normalize,
    get_or_create_company,
    get_or_create_skill,
)


@dataclass
class JobFullProfile:
    job: Job
    skill_requirements: list[tuple[JobSkillRequirement, Skill | None]] = field(
        default_factory=list,
    )
    organization: Organization | None = None
    company: Company | None = None
    location: Location | None = None


def create_job(db: Session, data: dict[str, Any]) -> Job:
    job_id = data.get("id") or uuid.uuid4()
    if isinstance(job_id, str):
        job_id = UUID(job_id)

    payload = {
        "id": job_id,
        "organization_id": data.get("organization_id"),
        "title": data.get("title") or "Untitled Role",
        "title_normalized": _normalize(data.get("title") or ""),
        "company_name": data.get("company_name"),
        "company_normalized": _normalize(data.get("company_name") or ""),
        "summary": data.get("summary"),
        "description_text": data.get("description_text") or data.get("description"),
        "description_html": data.get("description_html"),
        "requirements": data.get("requirements"),
        "role_family": data.get("role_family"),
        "employment_type": data.get("employment_type") or "full_time",
        "seniority_level": data.get("seniority_level"),
        "experience_level": data.get("experience_level"),
        "min_years_experience": data.get("min_years_experience"),
        "max_years_experience": data.get("max_years_experience"),
        "workplace_type": data.get("workplace_type"),
        "location_text": data.get("location_text"),
        "location_normalized": data.get("location_normalized"),
        "location_mode": data.get("location_mode")
        or data.get("work_mode")
        or "remote",
        "country_code": data.get("country_code"),
        "city": data.get("city"),
        "department": data.get("department"),
        "salary_min": data.get("salary_min"),
        "salary_max": data.get("salary_max"),
        "salary_currency": data.get("salary_currency"),
        "source_type": data.get("source_type") or "manual",
        "source_name": data.get("source_name"),
        "source_job_id": data.get("source_job_id"),
        "source_url": data.get("source_url"),
        "canonical_hash": data.get("canonical_hash"),
        "status": data.get("status") or "draft",
        "is_active": data.get("is_active", True),
        "raw_payload_jsonb": data.get("raw_payload_jsonb"),
    }

    job = Job(
        **{
            k: v
            for k, v in payload.items()
            if v is not None
            or k
            in {
                "raw_payload_jsonb",
                "salary_min",
                "salary_max",
                "summary",
                "min_years_experience",
                "max_years_experience",
                "workplace_type",
            }
        }
    )
    db.add(job)
    db.flush()
    return job


def update_job(db: Session, job_id: UUID | str, data: dict[str, Any]) -> Job:
    jid = UUID(str(job_id))
    job = db.get(Job, jid)
    if job is None:
        raise LookupError(f"Job {jid} not found")
    for f in (
        "organization_id",
        "title",
        "company_name",
        "description_text",
        "description_html",
        "requirements",
        "role_family",
        "employment_type",
        "seniority_level",
        "experience_level",
        "location_text",
        "location_mode",
        "country_code",
        "city",
        "department",
        "salary_min",
        "salary_max",
        "salary_currency",
        "status",
        "is_active",
        "raw_payload_jsonb",
    ):
        if f in data and data[f] is not None:
            setattr(job, f, data[f])
    if data.get("title"):
        job.title_normalized = _normalize(data["title"])
    if data.get("company_name"):
        job.company_normalized = _normalize(data["company_name"])
    db.flush()
    return job


def get_job(db: Session, job_id: UUID | str) -> Job | None:
    return db.get(Job, UUID(str(job_id)))


def get_job_full_profile(
    db: Session, job_id: UUID | str,
) -> JobFullProfile | None:
    jid = UUID(str(job_id))
    job = db.get(Job, jid)
    if job is None:
        return None

    profile = JobFullProfile(job=job)
    if job.organization_id:
        profile.organization = db.get(Organization, job.organization_id)

    if job.company_normalized:
        profile.company = db.execute(
            select(Company).where(Company.normalized_name == job.company_normalized)
        ).scalar_one_or_none()

    skill_rows = db.execute(
        select(JobSkillRequirement).where(JobSkillRequirement.job_id == jid)
    ).scalars().all()
    paired: list[tuple[JobSkillRequirement, Skill | None]] = []
    for jsr in skill_rows:
        sk = db.execute(
            select(Skill).where(Skill.normalized_name == jsr.skill_name_normalized)
        ).scalar_one_or_none()
        paired.append((jsr, sk))
    profile.skill_requirements = paired
    return profile


def upsert_job_required_skill(
    db: Session,
    job_id: UUID | str,
    skill_data: dict[str, Any],
) -> JobSkillRequirement:
    jid = UUID(str(job_id))
    raw_name = skill_data.get("name") or skill_data.get("skill_name_raw") or ""
    if not raw_name:
        raise ValueError("skill name required")
    normalized = _normalize(raw_name)
    skill = get_or_create_skill(db, raw_name, category=skill_data.get("category"))

    existing = db.execute(
        select(JobSkillRequirement).where(
            JobSkillRequirement.job_id == jid,
            JobSkillRequirement.skill_name_normalized == normalized,
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = JobSkillRequirement(
            job_id=jid,
            skill_name_raw=raw_name,
            skill_name_normalized=normalized,
        )
        db.add(existing)

    if "importance_weight" in skill_data:
        existing.importance_weight = skill_data["importance_weight"]
    if "is_required" in skill_data:
        existing.is_required = bool(skill_data["is_required"])
    if "extracted_by" in skill_data:
        existing.extracted_by = skill_data["extracted_by"]

    # Touch the canonical skill so it stays in sync (no-op if same)
    _ = skill
    db.flush()
    return existing


def job_summary_counts(db: Session, job_id: UUID | str) -> dict[str, int]:
    jid = UUID(str(job_id))
    skill_rows = db.execute(
        select(JobSkillRequirement).where(JobSkillRequirement.job_id == jid)
    ).all()
    return {
        "required_skills_count": len(skill_rows),
    }
