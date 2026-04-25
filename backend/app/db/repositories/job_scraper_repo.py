"""
PATHS Backend — Job-scraper relational repository.

Implements the spec-required helpers from `02_POSTGRES_JOB_IMPORT_REQUIREMENTS.md`:

  - upsert_company(name) -> Company
  - upsert_skills(names) -> dict[name, Skill]
  - upsert_job(NormalizedJob, company_id) -> (job, operation)
  - replace_job_skills(...)
  - replace_job_requirements(...)
  - replace_job_responsibilities(...)
  - create_import_run(...) / finish_import_run(...) / log_import_error(...)
  - get_state(source) / advance_state(source, count, new_offset)

It deliberately uses only the spec-compliant new tables (`job_skills`,
`job_requirements`, `job_responsibilities`, `job_import_runs`,
`job_import_errors`, `job_scraper_state`) and the existing canonical
`jobs`, `companies`, `skills` tables. The legacy
`job_skill_requirements` / `job_source_runs` rows produced by
`job_ingestion_service` are not touched here.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.cv_entities import Skill
from app.db.models.job import Job
from app.db.models.job_scraper import (
    JobImportError,
    JobImportRun,
    JobRequirementText,
    JobResponsibility,
    JobScraperState,
    JobSkillLink,
)
from app.db.models.reference import Company
from app.services.job_scraper.job_deduplication import (
    find_existing,
    normalize_for_match,
)
from app.services.job_scraper.job_normalizer import NormalizedJob

logger = logging.getLogger(__name__)


# ── Companies / Skills ───────────────────────────────────────────────────


def upsert_company(
    db: Session, name: str, *, raw_payload: dict[str, Any] | None = None,
) -> Company:
    normalized = normalize_for_match(name)
    if not normalized:
        raise ValueError("company name is required")
    existing = db.execute(
        select(Company).where(Company.normalized_name == normalized)
    ).scalar_one_or_none()
    if existing:
        return existing
    company = Company(name=name.strip(), normalized_name=normalized)
    db.add(company)
    db.flush()
    return company


def upsert_skill(db: Session, canonical_name: str) -> Skill:
    name = canonical_name.strip()
    normalized = name.lower()
    existing = db.execute(
        select(Skill).where(Skill.normalized_name == normalized)
    ).scalar_one_or_none()
    if existing:
        return existing
    skill = Skill(normalized_name=normalized)
    db.add(skill)
    db.flush()
    return skill


def upsert_skills(db: Session, names: list[str]) -> dict[str, Skill]:
    out: dict[str, Skill] = {}
    for name in names:
        if not name:
            continue
        out[name] = upsert_skill(db, name)
    return out


# ── Jobs ─────────────────────────────────────────────────────────────────


def _job_text_hash(normalized: NormalizedJob) -> str:
    payload = "|".join([
        normalized.title or "",
        normalized.company_name or "",
        normalized.summary or "",
        normalized.description or "",
        ";".join(normalized.requirements),
        ";".join(normalized.responsibilities),
        ";".join(normalized.required_skills),
        ";".join(normalized.preferred_skills),
        normalized.workplace_type or "",
        normalized.location_text or "",
        str(normalized.min_years_experience or ""),
        str(normalized.max_years_experience or ""),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_job(
    db: Session, normalized: NormalizedJob, company: Company,
) -> tuple[Job, str]:
    """Insert or update a Job row.

    Returns ``(job, operation)`` where ``operation`` is one of
    ``"inserted" | "updated" | "skipped"``. ``skipped`` is returned when
    the row already exists with the same ``text_hash`` (no changes).
    """
    title_norm = normalize_for_match(normalized.title)
    company_norm = normalize_for_match(normalized.company_name)
    location_norm = normalize_for_match(normalized.location_text)
    text_hash = _job_text_hash(normalized)
    now = datetime.now(timezone.utc)

    existing = find_existing(db, normalized)
    if existing is None:
        job = Job(
            title=normalized.title,
            title_normalized=title_norm,
            company_id=company.id,
            company_name=normalized.company_name,
            company_normalized=company_norm,
            summary=normalized.summary,
            description_text=normalized.description,
            requirements=("\n".join(normalized.requirements) or None),
            employment_type=normalized.employment_type or "full_time",
            seniority_level=normalized.seniority_level,
            experience_level=normalized.seniority_level,
            workplace_type=normalized.workplace_type,
            min_years_experience=normalized.min_years_experience,
            max_years_experience=normalized.max_years_experience,
            location_text=normalized.location_text,
            location_normalized=location_norm or None,
            location_mode=normalized.workplace_type or "unknown",
            source_platform=normalized.source_platform,
            source_type=normalized.source_platform,
            source_name=normalized.source_platform,
            source_url=normalized.source_url,
            source_external_id=None,
            posted_at=normalized.posted_at,
            scraped_at=normalized.scraped_at,
            salary_min=normalized.salary_min,
            salary_max=normalized.salary_max,
            salary_currency=normalized.salary_currency,
            status="active",
            is_active=True,
            graph_sync_status="pending",
            vector_sync_status="pending",
            last_imported_at=now,
            text_hash=text_hash,
            raw_payload_jsonb=normalized.raw_payload,
        )
        db.add(job)
        db.flush()
        return job, "inserted"

    # Compare with existing row → update only when something changed
    changed = False
    if existing.text_hash != text_hash:
        changed = True

    # Always refresh source/company linkage even if hash matches
    existing.company_id = company.id
    existing.company_name = normalized.company_name
    existing.company_normalized = company_norm
    existing.source_platform = normalized.source_platform
    existing.source_url = normalized.source_url

    if not changed:
        existing.last_imported_at = now
        return existing, "skipped"

    existing.title = normalized.title
    existing.title_normalized = title_norm
    existing.summary = normalized.summary
    existing.description_text = normalized.description
    existing.requirements = "\n".join(normalized.requirements) or None
    existing.employment_type = normalized.employment_type or existing.employment_type
    existing.seniority_level = normalized.seniority_level
    existing.experience_level = normalized.seniority_level
    existing.workplace_type = normalized.workplace_type
    existing.min_years_experience = normalized.min_years_experience
    existing.max_years_experience = normalized.max_years_experience
    existing.location_text = normalized.location_text
    existing.location_normalized = location_norm or None
    existing.location_mode = normalized.workplace_type or existing.location_mode
    existing.posted_at = normalized.posted_at or existing.posted_at
    existing.scraped_at = normalized.scraped_at
    existing.salary_min = normalized.salary_min
    existing.salary_max = normalized.salary_max
    existing.salary_currency = normalized.salary_currency
    existing.is_active = True
    existing.status = existing.status or "active"
    existing.graph_sync_status = "pending"
    existing.vector_sync_status = "pending"
    existing.last_imported_at = now
    existing.text_hash = text_hash
    existing.raw_payload_jsonb = normalized.raw_payload
    db.flush()
    return existing, "updated"


def replace_job_skills(
    db: Session,
    job_id: UUID,
    *,
    required_skills: list[str],
    preferred_skills: list[str],
) -> tuple[int, int]:
    """Replace the spec `job_skills` rows for this job."""
    db.execute(delete(JobSkillLink).where(JobSkillLink.job_id == job_id))

    skill_objs = upsert_skills(db, required_skills + preferred_skills)
    inserted_required = 0
    inserted_preferred = 0
    for name in required_skills:
        skill = skill_objs.get(name)
        if not skill:
            continue
        db.add(JobSkillLink(
            job_id=job_id,
            skill_id=skill.id,
            requirement_type="required",
            importance_score=1.0,
        ))
        inserted_required += 1
    for name in preferred_skills:
        skill = skill_objs.get(name)
        if not skill:
            continue
        db.add(JobSkillLink(
            job_id=job_id,
            skill_id=skill.id,
            requirement_type="preferred",
            importance_score=0.5,
        ))
        inserted_preferred += 1
    db.flush()
    return inserted_required, inserted_preferred


def replace_job_requirements(
    db: Session, job_id: UUID, requirements: list[str],
) -> int:
    db.execute(
        delete(JobRequirementText).where(JobRequirementText.job_id == job_id)
    )
    count = 0
    for text in requirements:
        text = text.strip()
        if not text:
            continue
        db.add(JobRequirementText(job_id=job_id, requirement_text=text))
        count += 1
    db.flush()
    return count


def replace_job_responsibilities(
    db: Session, job_id: UUID, responsibilities: list[str],
) -> int:
    db.execute(
        delete(JobResponsibility).where(JobResponsibility.job_id == job_id)
    )
    count = 0
    for text in responsibilities:
        text = text.strip()
        if not text:
            continue
        db.add(JobResponsibility(job_id=job_id, responsibility_text=text))
        count += 1
    db.flush()
    return count


# ── Sync status helpers (mirrors `db_sync_status`) ──────────────────────


def mark_graph_sync(
    db: Session, job_id: UUID, *, status: str, error: str | None = None,
) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.graph_sync_status = status
    if status == "synced":
        job.last_graph_sync_at = datetime.now(timezone.utc)


def mark_vector_sync(
    db: Session, job_id: UUID, *, status: str, error: str | None = None,
) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.vector_sync_status = status
    if status == "synced":
        job.last_vector_sync_at = datetime.now(timezone.utc)


# ── Import run logging ──────────────────────────────────────────────────


def create_import_run(
    db: Session,
    *,
    source_platform: str,
    requested_limit: int,
    metadata: dict[str, Any] | None = None,
) -> JobImportRun:
    run = JobImportRun(
        source_platform=source_platform,
        requested_limit=requested_limit,
        status="running",
        run_metadata=metadata,
    )
    db.add(run)
    db.flush()
    return run


def finish_import_run(
    db: Session,
    run: JobImportRun,
    *,
    status: str,
    counts: dict[str, int],
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> JobImportRun:
    run.finished_at = datetime.now(timezone.utc)
    run.status = status
    run.scraped_count = counts.get("scraped_count", 0)
    run.valid_count = counts.get("valid_count", 0)
    run.inserted_count = counts.get("inserted_count", 0)
    run.updated_count = counts.get("updated_count", 0)
    run.skipped_count = counts.get("skipped_count", 0)
    run.failed_count = counts.get("failed_count", 0)
    run.graph_synced_count = counts.get("graph_synced_count", 0)
    run.vector_synced_count = counts.get("vector_synced_count", 0)
    if error_message is not None:
        run.error_message = error_message
    if metadata is not None:
        run.run_metadata = {**(run.run_metadata or {}), **metadata}
    db.flush()
    return run


def log_import_error(
    db: Session,
    *,
    import_run_id: UUID | None,
    source_platform: str | None,
    source_url: str | None,
    job_title: str | None,
    company_name: str | None,
    error_type: str,
    error_message: str,
    raw_payload: dict[str, Any] | None = None,
) -> JobImportError:
    err = JobImportError(
        import_run_id=import_run_id,
        source_platform=source_platform,
        source_url=source_url,
        job_title=(job_title or "")[:500] or None,
        company_name=(company_name or "")[:500] or None,
        error_type=error_type[:100] if error_type else None,
        error_message=error_message,
        raw_payload=raw_payload,
    )
    db.add(err)
    db.flush()
    return err


# ── Scraper rolling state ───────────────────────────────────────────────


def get_state(db: Session, source_platform: str) -> JobScraperState:
    state = db.execute(
        select(JobScraperState).where(JobScraperState.source_platform == source_platform)
    ).scalar_one_or_none()
    if state is None:
        state = JobScraperState(source_platform=source_platform, company_offset=0)
        db.add(state)
        db.flush()
    return state


def advance_state(
    db: Session,
    *,
    source_platform: str,
    new_offset: int,
    last_imported_count: int,
) -> JobScraperState:
    state = get_state(db, source_platform)
    state.company_offset = max(0, int(new_offset))
    state.last_imported_count = int(last_imported_count)
    state.last_run_at = datetime.now(timezone.utc)
    db.flush()
    return state


# ── Recent runs / history ───────────────────────────────────────────────


def list_import_runs(db: Session, *, limit: int = 25) -> list[JobImportRun]:
    return list(
        db.execute(
            select(JobImportRun).order_by(JobImportRun.started_at.desc()).limit(limit)
        ).scalars().all()
    )


def get_latest_import_run(db: Session) -> JobImportRun | None:
    return db.execute(
        select(JobImportRun).order_by(JobImportRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()


def list_failed_jobs_for_retry(db: Session, *, limit: int = 25) -> list[Job]:
    """Jobs whose graph or vector sync still needs to be retried."""
    return list(
        db.execute(
            select(Job)
            .where(
                (Job.graph_sync_status.in_(["pending", "failed"]))
                | (Job.vector_sync_status.in_(["pending", "failed"]))
            )
            .order_by(Job.last_imported_at.desc().nullslast())
            .limit(limit)
        ).scalars().all()
    )
