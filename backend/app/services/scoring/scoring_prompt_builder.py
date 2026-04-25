"""
PATHS Backend — Scoring prompt builder.

Implements:

  * ``anonymize_candidate(profile)`` — strip protected attributes
    (name, email, phone, photo, gender, age, religion, etc.) before any
    candidate data is sent to the LLM.
  * ``anonymize_job(profile)`` — strip noisy / ID-shaped fields the
    agent doesn't need.
  * ``build_messages(...)`` — return the OpenRouter chat messages
    (system + user) including the criteria definition and the
    JSON-only output schema.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from app.db.repositories.candidates_relational import CandidateFullProfile
from app.db.repositories.jobs_relational import JobFullProfile
from app.services.scoring.scoring_criteria import (
    DEFAULT_CRITERIA,
    empty_criteria_payload,
)

# ── Protected attributes (never leave this module) ───────────────────────


PROTECTED_FIELDS: frozenset[str] = frozenset({
    "full_name",
    "name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "phone_number",
    "photo",
    "photo_url",
    "image",
    "image_url",
    "avatar",
    "avatar_url",
    "gender",
    "sex",
    "age",
    "date_of_birth",
    "dob",
    "marital_status",
    "religion",
    "nationality",
    "citizenship",
    "address",
    "street_address",
    "postal_code",
    "zip_code",
    "city_of_residence",
    "ssn",
    "national_id",
    "passport",
    "tax_id",
    "disability",
    "political_views",
    "race",
    "ethnicity",
    "social_security_number",
})


def _strip_dict(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k.lower() not in PROTECTED_FIELDS}


# ── Candidate anonymization ──────────────────────────────────────────────


def anonymize_candidate(
    profile: CandidateFullProfile, *, candidate_id: str | None = None,
) -> dict[str, Any]:
    """Build a job-only view of the candidate safe to send to the LLM.

    The candidate full name, email, phone, etc. are dropped. Only
    skills, experience, education, projects, certifications, links
    deemed job-relevant (GitHub / portfolio), and high-level location
    flags remain.
    """
    c = profile.candidate
    skills = []
    for cs, sk in profile.skills:
        skills.append({
            "name": sk.normalized_name,
            "category": sk.category,
            "proficiency_score": cs.proficiency_score,
            "years_used": cs.years_used,
            "evidence": (cs.evidence_text or "")[:400] or None,
        })

    experiences = []
    for exp, _co in profile.experiences:
        experiences.append({
            "title": exp.title,
            "company": exp.company_name,
            "start_date": exp.start_date,
            "end_date": exp.end_date,
            "summary": (exp.description or "")[:400] or None,
        })

    education = [
        {
            "institution": e.institution,
            "degree": e.degree,
            "field_of_study": e.field_of_study,
            "start_date": e.start_date,
            "end_date": e.end_date,
        }
        for e in profile.education
    ]

    projects = [
        {
            "name": p.name,
            "description": (p.description or "")[:400] or None,
            "technologies": p.technologies or [],
            "repository_url": p.repository_url,
        }
        for p in profile.projects
    ]

    certifications = [
        {"name": k.name, "issuer": k.issuer} for k in profile.certifications
    ]

    relevant_links = [
        {"link_type": link.link_type, "url": link.url}
        for link in profile.links
        if link.link_type
        and link.link_type.lower() in {"github", "gitlab", "portfolio", "website", "stackoverflow"}
    ]

    location_flag = c.location_text or None
    summary = (c.summary or "")[:1500] or None

    return {
        "candidate_ref": candidate_id or "anonymous",
        "current_title": c.current_title,
        "headline": c.headline,
        "years_of_experience": c.years_experience,
        "summary": summary,
        "location_flag": location_flag,
        "skills": skills,
        "experience": experiences,
        "education": education,
        "projects": projects,
        "certifications": certifications,
        "links": relevant_links,
    }


# ── Job anonymization (only structural noise removed) ───────────────────


def anonymize_job(profile: JobFullProfile, *, job_id: str | None = None) -> dict[str, Any]:
    j = profile.job
    skills_required: list[str] = []
    skills_preferred: list[str] = []
    for jsr, sk in profile.skill_requirements:
        name = (sk.normalized_name if sk else jsr.skill_name_normalized) or ""
        if not name:
            continue
        if jsr.is_required:
            skills_required.append(name)
        else:
            skills_preferred.append(name)

    return {
        "job_ref": job_id or str(j.id),
        "title": j.title,
        "company": (
            profile.company.name if profile.company else j.company_name
        ),
        "summary": j.summary,
        "description": (j.description_text or "")[:4000] or None,
        "requirements": j.requirements,
        "seniority_level": j.seniority_level,
        "experience_level": j.experience_level,
        "min_years_experience": j.min_years_experience,
        "max_years_experience": j.max_years_experience,
        "employment_type": j.employment_type,
        "workplace_type": j.workplace_type or j.location_mode,
        "location": j.location_text,
        "salary_min": float(j.salary_min) if j.salary_min is not None else None,
        "salary_max": float(j.salary_max) if j.salary_max is not None else None,
        "salary_currency": j.salary_currency,
        "required_skills": skills_required,
        "preferred_skills": skills_preferred,
    }


# ── Prompt construction ─────────────────────────────────────────────────


_SYSTEM_PROMPT = """You are PATHS Scoring Agent, an expert recruitment matching assistant.

Your task is to evaluate how well an anonymized candidate matches a specific job.

You must be fair, evidence-based, and strict.

Do NOT use protected attributes.
Do NOT infer gender, age, religion, nationality, or personal identity.
Do NOT reward or penalize based on name, photo, demographic details, or personal background.
Only use skills, experience, projects, education, certifications, job requirements, and job preferences.

Return ONLY valid JSON that matches the requested schema. No prose. No code fences.
"""


def _criteria_summary() -> str:
    lines = []
    for c in DEFAULT_CRITERIA:
        lines.append(f"- {c.label}: {c.max_score} points — {c.description}")
    return "\n".join(lines)


_OUTPUT_SCHEMA = {
    "agent_score": 0,
    "criteria_breakdown": empty_criteria_payload(),
    "matched_skills": [],
    "missing_required_skills": [],
    "missing_preferred_skills": [],
    "strengths": [],
    "weaknesses": [],
    "recommendation": "strong_match | good_match | possible_match | weak_match | not_recommended",
    "explanation": "",
    "confidence": 0.0,
}


def build_messages(
    anonymized_candidate: dict[str, Any],
    anonymized_job: dict[str, Any],
) -> list[dict[str, str]]:
    """Return the OpenRouter chat-completions messages list."""
    user_payload = {
        "candidate": _strip_dict(anonymized_candidate),
        "job": _strip_dict(anonymized_job),
    }
    user_prompt = (
        "Scoring criteria (the six component scores must sum to agent_score):\n"
        f"{_criteria_summary()}\n\n"
        "Candidate and job data follow as JSON.\n\n"
        f"DATA:\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}\n\n"
        "Required output JSON schema (return ONLY this JSON object):\n"
        f"{json.dumps(_OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}\n\n"
        "Hard rules:\n"
        " - agent_score must be an integer between 0 and 100.\n"
        " - The six criteria_breakdown.*.score values must sum to agent_score.\n"
        " - confidence must be a number between 0.0 and 1.0.\n"
        " - recommendation must be one of: "
        "strong_match, good_match, possible_match, weak_match, not_recommended.\n"
        " - matched_skills, missing_required_skills, missing_preferred_skills, "
        "strengths, weaknesses must be arrays of short strings.\n"
        " - Do NOT include candidate name, email, phone, photo, gender, age, "
        "religion, or any protected attribute in your output.\n"
        " - Output JSON ONLY. No markdown. No code fences. No commentary."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT.strip()},
        {"role": "user", "content": user_prompt},
    ]


# ── Helpers usable by tests / fallback agent ────────────────────────────


def coerce_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"cannot coerce {type(value)!r} to dict")


__all__ = [
    "PROTECTED_FIELDS",
    "anonymize_candidate",
    "anonymize_job",
    "build_messages",
    "coerce_to_dict",
]
