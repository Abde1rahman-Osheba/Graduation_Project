"""
PATHS Backend — Candidate graph repository (Apache AGE).

Implements spec-required functions from
`03_GRAPH_APACHE_AGE_ONTOLOGY_REQUIREMENTS.md`. Every Candidate node
created here uses the canonical PostgreSQL `candidate_id` as the
`candidate_id` property (never an AGE internal id).

The Cypher snippets below intentionally use parameterized values via
`age_query.run_cypher`, which centralizes safe parameter substitution.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.repositories.candidates_relational import (
    CandidateFullProfile,
    _normalize,
)
from app.utils.age_query import run_cypher


# ── Candidate node ───────────────────────────────────────────────────────


def upsert_candidate_node(
    db: Session, profile: CandidateFullProfile,
) -> None:
    c = profile.candidate
    cypher = """
    MERGE (c:Candidate {candidate_id: $candidate_id})
    SET c.full_name = $full_name,
        c.headline = $headline,
        c.current_title = $current_title,
        c.years_of_experience = $years_of_experience,
        c.seniority_level = $seniority_level,
        c.open_to_work = $open_to_work,
        c.updated_at = $updated_at
    RETURN c
    """
    run_cypher(
        db,
        cypher,
        {
            "candidate_id": str(c.id),
            "full_name": c.full_name or "",
            "headline": c.headline or "",
            "current_title": c.current_title or "",
            "years_of_experience": c.years_experience or 0,
            "seniority_level": "",  # spec field; populated when seniority is known
            "open_to_work": True,
            "updated_at": (c.updated_at or c.created_at).isoformat()
            if c.updated_at or c.created_at
            else "",
        },
    )


# ── Candidate skills ─────────────────────────────────────────────────────


def upsert_candidate_skills(
    db: Session, profile: CandidateFullProfile,
) -> int:
    count = 0
    for cs, sk in profile.skills:
        cypher = """
        MERGE (c:Candidate {candidate_id: $candidate_id})
        MERGE (s:Skill {skill_id: $skill_id})
        SET s.name = $skill_name,
            s.normalized_name = $normalized_skill_name,
            s.category = $skill_category
        MERGE (c)-[r:HAS_SKILL]->(s)
        SET r.proficiency_score = $proficiency_score,
            r.years_of_experience = $years_of_experience,
            r.evidence = $evidence,
            r.source = $source
        RETURN r
        """
        run_cypher(
            db,
            cypher,
            {
                "candidate_id": str(profile.candidate.id),
                "skill_id": str(sk.id),
                "skill_name": sk.normalized_name,
                "normalized_skill_name": sk.normalized_name,
                "skill_category": sk.category or "",
                "proficiency_score": cs.proficiency_score or 0,
                "years_of_experience": cs.years_used or 0,
                "evidence": cs.evidence_text or "",
                "source": "cv",
            },
        )
        count += 1
    return count


# ── Candidate experiences (HAS_EXPERIENCE / WORKED_AT / AT_COMPANY) ──────


def upsert_candidate_experiences(
    db: Session, profile: CandidateFullProfile,
) -> int:
    count = 0
    for exp, company in profile.experiences:
        company_name = (exp.company_name or "").strip()
        if not company_name:
            continue
        company_id = str(company.id) if company else f"company:{_normalize(company_name)}"
        cypher = """
        MERGE (c:Candidate {candidate_id: $candidate_id})
        MERGE (co:Company {company_id: $company_id})
        SET co.name = $company_name,
            co.normalized_name = $normalized_company_name
        MERGE (e:Experience {experience_id: $experience_id})
        SET e.candidate_id = $candidate_id,
            e.job_title = $job_title,
            e.start_date = $start_date,
            e.end_date = $end_date,
            e.summary = $summary
        MERGE (c)-[hx:HAS_EXPERIENCE]->(e)
        SET hx.is_current = $is_current
        MERGE (c)-[w:WORKED_AT]->(co)
        SET w.experience_id = $experience_id,
            w.job_title = $job_title,
            w.start_date = $start_date,
            w.end_date = $end_date,
            w.is_current = $is_current
        MERGE (e)-[at:AT_COMPANY]->(co)
        SET at.job_title = $job_title
        RETURN e
        """
        run_cypher(
            db,
            cypher,
            {
                "candidate_id": str(profile.candidate.id),
                "company_id": company_id,
                "company_name": company_name,
                "normalized_company_name": _normalize(company_name),
                "experience_id": str(exp.id),
                "job_title": exp.title or "",
                "start_date": exp.start_date or "",
                "end_date": exp.end_date or "",
                "summary": exp.description or "",
                "is_current": (exp.end_date is None or exp.end_date == ""),
            },
        )
        count += 1
    return count


# ── Education / projects / certifications ────────────────────────────────


def upsert_candidate_education(
    db: Session, profile: CandidateFullProfile,
) -> int:
    count = 0
    for edu in profile.education:
        if not edu.institution:
            continue
        cypher = """
        MERGE (c:Candidate {candidate_id: $candidate_id})
        MERGE (edu:Education {education_id: $education_id})
        SET edu.candidate_id = $candidate_id,
            edu.institution_name = $institution_name,
            edu.degree = $degree,
            edu.field_of_study = $field_of_study
        MERGE (c)-[r:STUDIED_AT]->(edu)
        RETURN r
        """
        run_cypher(
            db,
            cypher,
            {
                "candidate_id": str(profile.candidate.id),
                "education_id": str(edu.id),
                "institution_name": edu.institution,
                "degree": edu.degree or "",
                "field_of_study": edu.field_of_study or "",
            },
        )
        count += 1
    return count


def upsert_candidate_projects(
    db: Session, profile: CandidateFullProfile,
) -> int:
    count = 0
    for proj in profile.projects:
        cypher = """
        MERGE (c:Candidate {candidate_id: $candidate_id})
        MERGE (p:Project {project_id: $project_id})
        SET p.candidate_id = $candidate_id,
            p.name = $name,
            p.description = $description,
            p.repository_url = $repository_url
        MERGE (c)-[r:HAS_PROJECT]->(p)
        RETURN r
        """
        run_cypher(
            db,
            cypher,
            {
                "candidate_id": str(profile.candidate.id),
                "project_id": str(proj.id),
                "name": proj.name,
                "description": proj.description or "",
                "repository_url": proj.repository_url or "",
            },
        )
        count += 1
    return count


def upsert_candidate_certifications(
    db: Session, profile: CandidateFullProfile,
) -> int:
    count = 0
    for cert in profile.certifications:
        cypher = """
        MERGE (c:Candidate {candidate_id: $candidate_id})
        MERGE (k:Certification {certification_id: $certification_id})
        SET k.candidate_id = $candidate_id,
            k.name = $name,
            k.issuer = $issuer
        MERGE (c)-[r:HAS_CERTIFICATION]->(k)
        RETURN r
        """
        run_cypher(
            db,
            cypher,
            {
                "candidate_id": str(profile.candidate.id),
                "certification_id": str(cert.id),
                "name": cert.name,
                "issuer": cert.issuer or "",
            },
        )
        count += 1
    return count


# ── Verification ─────────────────────────────────────────────────────────


def verify_candidate_graph(db: Session, candidate_id: UUID | str) -> dict[str, Any]:
    cid = str(candidate_id)
    exists_rows = run_cypher(
        db,
        """
        MATCH (c:Candidate {candidate_id: $candidate_id})
        RETURN c.candidate_id
        """,
        {"candidate_id": cid},
    )
    skill_rows = run_cypher(
        db,
        """
        MATCH (c:Candidate {candidate_id: $candidate_id})-[r:HAS_SKILL]->(s:Skill)
        RETURN s.normalized_name
        """,
        {"candidate_id": cid},
    )
    work_rows = run_cypher(
        db,
        """
        MATCH (c:Candidate {candidate_id: $candidate_id})-[r:WORKED_AT]->(co:Company)
        RETURN co.normalized_name
        """,
        {"candidate_id": cid},
    )
    exp_rows = run_cypher(
        db,
        """
        MATCH (c:Candidate {candidate_id: $candidate_id})-[r:HAS_EXPERIENCE]->(e:Experience)
        RETURN e.experience_id
        """,
        {"candidate_id": cid},
    )
    return {
        "exists": len(exists_rows) > 0,
        "has_skill_edges": len(skill_rows),
        "worked_at_edges": len(work_rows),
        "has_experience_edges": len(exp_rows),
    }
