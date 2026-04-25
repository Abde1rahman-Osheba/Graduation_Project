"""
PATHS Backend — Vector text builders for one-vector-per-entity.

Constructs the canonical text representation of a candidate / job that is
embedded into a single Qdrant vector. The templates are taken directly
from `04_QDRANT_VECTOR_REQUIREMENTS.md` and must remain stable so that
embeddings are reproducible.
"""

from __future__ import annotations

import hashlib
from typing import Iterable

from app.db.repositories.candidates_relational import CandidateFullProfile
from app.db.repositories.jobs_relational import JobFullProfile
from app.services.cv_sanitization_service import sanitize_cv_text


def _line(label: str, value: object) -> str:
    if value is None or value == "" or value == []:
        return f"{label}: -"
    return f"{label}: {value}"


def _join_nonempty(parts: Iterable[str]) -> str:
    return "\n".join(p for p in parts if p)


# ── Candidate ────────────────────────────────────────────────────────────


def build_candidate_vector_text(profile: CandidateFullProfile) -> str:
    c = profile.candidate

    skills_lines: list[str] = []
    for cs, sk in profile.skills:
        skills_lines.append(
            f"- {sk.normalized_name} (proficiency: {cs.proficiency_score or '-'}, "
            f"years: {cs.years_used or '-'}, evidence: {cs.evidence_text or '-'})"
        )

    experience_lines: list[str] = []
    for exp, _co in profile.experiences:
        experience_lines.append(
            f"- {exp.title or '-'} at {exp.company_name or '-'}, "
            f"{exp.start_date or '-'} to {exp.end_date or '-'}"
        )
        if exp.description:
            experience_lines.append(f"  Summary: {exp.description}")

    education_lines: list[str] = []
    for edu in profile.education:
        education_lines.append(
            f"- {edu.degree or '-'} in {edu.field_of_study or '-'} "
            f"from {edu.institution or '-'}"
        )

    project_lines: list[str] = []
    for p in profile.projects:
        techs = ", ".join(p.technologies or []) if p.technologies else "-"
        project_lines.append(f"- {p.name}: {p.description or '-'}. Technologies: {techs}")

    cert_lines = [
        f"- {cert.name} by {cert.issuer or '-'}" for cert in profile.certifications
    ]

    sanitized_doc = ""
    if profile.documents:
        # Use the most recent document with text
        for doc in sorted(
            profile.documents, key=lambda d: d.created_at or 0, reverse=True,
        ):
            if doc.raw_text:
                sanitized_doc = sanitize_cv_text(doc.raw_text)
                break

    sections = [
        "Entity Type: Candidate",
        _line("Candidate ID", str(c.id)),
        _line("Headline", c.headline or ""),
        _line("Current Title", c.current_title or ""),
        _line("Location", c.location_text or ""),
        _line("Years of Experience", c.years_experience or ""),
        "",
        "Professional Summary:",
        c.summary or "-",
        "",
        "Skills:",
        _join_nonempty(skills_lines) or "-",
        "",
        "Work Experience:",
        _join_nonempty(experience_lines) or "-",
        "",
        "Education:",
        _join_nonempty(education_lines) or "-",
        "",
        "Projects:",
        _join_nonempty(project_lines) or "-",
        "",
        "Certifications:",
        _join_nonempty(cert_lines) or "-",
    ]
    if sanitized_doc:
        sections.extend(["", "Sanitized CV Text:", sanitized_doc])

    return "\n".join(sections).strip()


# ── Job ──────────────────────────────────────────────────────────────────


def build_job_vector_text(profile: JobFullProfile) -> str:
    j = profile.job
    org_id = str(j.organization_id) if j.organization_id else ""
    company = (
        profile.company.name
        if profile.company
        else j.company_name or ""
    )

    skills_lines: list[str] = []
    for jsr, sk in profile.skill_requirements:
        skills_lines.append(
            f"- {jsr.skill_name_normalized} (type: "
            f"{'required' if jsr.is_required else 'preferred'}, "
            f"weight: {jsr.importance_weight})"
        )

    sections = [
        "Entity Type: Job",
        _line("Job ID", str(j.id)),
        _line("Organization ID", org_id),
        _line("Company", company),
        _line("Title", j.title or ""),
        _line("Seniority", j.seniority_level or ""),
        _line("Employment Type", j.employment_type or ""),
        _line("Work Mode", j.location_mode or ""),
        _line(
            "Location",
            ", ".join(filter(None, [j.city, j.country_code, j.location_text])),
        ),
        _line("Experience Level", j.experience_level or ""),
        "",
        "Job Description:",
        j.description_text or "-",
        "",
        "Requirements:",
        j.requirements or "-",
        "",
        "Required Skills:",
        _join_nonempty(skills_lines) or "-",
    ]
    return "\n".join(sections).strip()


# ── Hash helper ──────────────────────────────────────────────────────────


def text_source_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
