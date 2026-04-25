"""
PATHS Backend — Job graph repository (Apache AGE).

Implements `upsert_job_node`, `upsert_job_required_skills`,
`upsert_job_organization_edge`, and `verify_job_graph`. Every Job node
uses the canonical PostgreSQL `job_id`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.repositories.candidates_relational import _normalize
from app.db.repositories.jobs_relational import JobFullProfile
from app.utils.age_query import run_cypher


def upsert_job_node(db: Session, profile: JobFullProfile) -> None:
    j = profile.job
    cypher = """
    MERGE (j:Job {job_id: $job_id})
    SET j.organization_id = $organization_id,
        j.title = $title,
        j.normalized_title = $normalized_title,
        j.seniority_level = $seniority_level,
        j.employment_type = $employment_type,
        j.work_mode = $work_mode,
        j.status = $status,
        j.updated_at = $updated_at
    RETURN j
    """
    run_cypher(
        db,
        cypher,
        {
            "job_id": str(j.id),
            "organization_id": str(j.organization_id) if j.organization_id else "",
            "title": j.title or "",
            "normalized_title": j.title_normalized or _normalize(j.title or ""),
            "seniority_level": j.seniority_level or "",
            "employment_type": j.employment_type or "",
            "work_mode": j.location_mode or "",
            "status": j.status or "",
            "updated_at": (j.updated_at or j.created_at).isoformat()
            if j.updated_at or j.created_at
            else "",
        },
    )


def upsert_job_required_skills(db: Session, profile: JobFullProfile) -> int:
    count = 0
    for jsr, skill in profile.skill_requirements:
        skill_id = str(skill.id) if skill else f"skill:{jsr.skill_name_normalized}"
        cypher = """
        MERGE (j:Job {job_id: $job_id})
        MERGE (s:Skill {skill_id: $skill_id})
        SET s.name = $skill_name,
            s.normalized_name = $normalized_skill_name,
            s.category = $skill_category
        MERGE (j)-[r:REQUIRES_SKILL]->(s)
        SET r.requirement_type = $requirement_type,
            r.importance_weight = $importance_weight
        RETURN r
        """
        run_cypher(
            db,
            cypher,
            {
                "job_id": str(profile.job.id),
                "skill_id": skill_id,
                "skill_name": jsr.skill_name_raw,
                "normalized_skill_name": jsr.skill_name_normalized,
                "skill_category": (skill.category if skill else "") or "",
                "requirement_type": "required" if jsr.is_required else "preferred",
                "importance_weight": float(jsr.importance_weight or 1.0),
            },
        )
        count += 1
    return count


def upsert_job_organization_edge(
    db: Session, profile: JobFullProfile,
) -> bool:
    org = profile.organization
    if org is None:
        return False
    cypher = """
    MERGE (o:Organization {organization_id: $organization_id})
    SET o.name = $name
    MERGE (j:Job {job_id: $job_id})
    MERGE (o)-[r:POSTED]->(j)
    SET r.status = $status
    RETURN r
    """
    run_cypher(
        db,
        cypher,
        {
            "organization_id": str(org.id),
            "name": org.name or "",
            "job_id": str(profile.job.id),
            "status": profile.job.status or "",
        },
    )
    return True


def verify_job_graph(db: Session, job_id: UUID | str) -> dict[str, Any]:
    jid = str(job_id)
    exists_rows = run_cypher(
        db,
        "MATCH (j:Job {job_id: $job_id}) RETURN j.job_id",
        {"job_id": jid},
    )
    skill_rows = run_cypher(
        db,
        """
        MATCH (j:Job {job_id: $job_id})-[r:REQUIRES_SKILL]->(s:Skill)
        RETURN s.normalized_name
        """,
        {"job_id": jid},
    )
    posted_rows = run_cypher(
        db,
        """
        MATCH (o:Organization)-[r:POSTED]->(j:Job {job_id: $job_id})
        RETURN o.organization_id
        """,
        {"job_id": jid},
    )
    return {
        "exists": len(exists_rows) > 0,
        "requires_skill_edges": len(skill_rows),
        "posted_by_edges": len(posted_rows),
    }
