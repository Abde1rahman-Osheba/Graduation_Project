"""
Normalize organization-submitted job requirements, persist `jobs` + `organization_job_requests`,
and sync to Apache AGE + Qdrant (one vector per job).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.organization_matching import OrganizationJobRequest
from app.db.repositories import jobs_relational, organization_matching_repo as om_repo
from app.services.job_sync_service import sync_job_full
from app.services.scoring.relevance_filter_service import infer_role_family, _build_haystack

logger = logging.getLogger(__name__)
settings = get_settings()


def _cap_top_k(top_k: int) -> int:
    k = top_k or settings.org_matching_default_top_k
    return max(1, min(int(k), int(settings.org_matching_max_top_k)))


def normalize_job_intake(
    organization_id: UUID,
    job_in: dict[str, Any],
    *,
    top_k: int = 3,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    """
    Returns dict with `top_k` and `normalized` payload for `create_or_update_path`.
    """
    k = _cap_top_k(int(top_k))
    title = (job_in.get("title") or "").strip() or "Open Role"
    required_skills = list(job_in.get("required_skills") or [])
    preferred_skills = list(job_in.get("preferred_skills") or [])

    hay = _build_haystack(
        title,
        job_in.get("summary"),
        " ".join(str(s) for s in required_skills),
    )
    role_family = infer_role_family(hay)

    res_parts: list[str] = []
    if job_in.get("responsibilities"):
        res_parts.append("Responsibilities:\n" + "\n".join(f"- {x}" for x in job_in["responsibilities"]))
    if job_in.get("requirements"):
        req = job_in["requirements"]
        if isinstance(req, list):
            res_parts.append("Requirements:\n" + "\n".join(f"- {x}" for x in req))
        else:
            res_parts.append(f"Requirements:\n{req}")
    description_text = "\n\n".join(res_parts) if res_parts else (job_in.get("summary") or "")

    normalized = {
        "organization_id": organization_id,
        "title": title,
        "summary": job_in.get("summary"),
        "description_text": description_text or job_in.get("summary") or title,
        "requirements": job_in.get("requirements") if isinstance(job_in.get("requirements"), str) else None,
        "role_family": job_in.get("role_family") or role_family,
        "employment_type": (job_in.get("employment_type") or "full_time").replace("-", "_"),
        "seniority_level": job_in.get("seniority_level"),
        "min_years_experience": job_in.get("min_years_experience"),
        "max_years_experience": job_in.get("max_years_experience"),
        "workplace_type": job_in.get("workplace_type"),
        "location_text": job_in.get("location_text"),
        "location_mode": job_in.get("workplace_type") or "remote",
        "salary_min": job_in.get("salary_min"),
        "salary_max": job_in.get("salary_max"),
        "salary_currency": job_in.get("salary_currency") or "USD",
        "source_type": "org_matching",
        "status": "active",
        "is_active": True,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
    }
    return {"top_k": k, "normalized": normalized, "request_payload": {
        "title": title,
        "summary": job_in.get("summary"),
        "description": description_text,
        "responsibilities": job_in.get("responsibilities"),
        "requirements": job_in.get("requirements"),
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "min_years_experience": job_in.get("min_years_experience"),
        "max_years_experience": job_in.get("max_years_experience"),
        "seniority_level": job_in.get("seniority_level"),
        "location_text": job_in.get("location_text"),
        "workplace_type": job_in.get("workplace_type"),
        "employment_type": job_in.get("employment_type") or "full_time",
        "education_requirements": job_in.get("education_requirements"),
        "salary_min": job_in.get("salary_min"),
        "salary_max": job_in.get("salary_max"),
        "salary_currency": job_in.get("salary_currency"),
        "role_family": normalized["role_family"],
        "top_k": k,
        "source_type": "manual",
        "status": "created",
        "created_by": created_by,
    }}


def persist_job_and_request(
    db: Session,
    *,
    organization_id: UUID,
    intake: dict[str, Any],
) -> tuple[OrganizationJobRequest, Any]:
    """Create `jobs` row, `organization_job_requests`, required skills, sync graph+vector."""
    n = intake["normalized"]
    rp = intake["request_payload"]
    top_k = intake["top_k"]

    job = jobs_relational.create_job(
        db,
        {
            "organization_id": organization_id,
            "title": n["title"],
            "summary": n.get("summary"),
            "description_text": n.get("description_text"),
            "requirements": n.get("requirements"),
            "role_family": n.get("role_family"),
            "employment_type": n.get("employment_type"),
            "seniority_level": n.get("seniority_level"),
            "min_years_experience": n.get("min_years_experience"),
            "max_years_experience": n.get("max_years_experience"),
            "workplace_type": n.get("workplace_type"),
            "location_text": n.get("location_text"),
            "location_mode": n.get("location_mode"),
            "salary_min": n.get("salary_min"),
            "salary_max": n.get("salary_max"),
            "salary_currency": n.get("salary_currency"),
            "source_type": n.get("source_type", "org_matching"),
            "status": n.get("status", "active"),
            "is_active": True,
        },
    )
    db.flush()

    for name in n.get("required_skills") or []:
        if name:
            jobs_relational.upsert_job_required_skill(
                db, job.id, {"name": str(name), "is_required": True},
            )
    for name in n.get("preferred_skills") or []:
        if name:
            jobs_relational.upsert_job_required_skill(
                db, job.id, {"name": str(name), "is_required": False},
            )

    db.commit()

    req = om_repo.create_job_request(
        db,
        {**rp, "organization_id": organization_id, "job_id": job.id, "top_k": top_k},
    )
    req.status = "linked"
    db.flush()
    db.commit()

    try:
        sync_job_full(db, job.id, force_vector=True)
    except Exception:  # noqa: BLE001
        logger.exception("Job sync (graph+vector) failed for job %s", job.id)

    return req, job
