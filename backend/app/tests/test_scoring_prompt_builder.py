"""Tests for the scoring prompt builder.

The most critical assertion: the messages returned to the LLM must
**never** contain protected attributes from the candidate profile
(name / email / phone / etc.).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.db.repositories.candidates_relational import CandidateFullProfile
from app.db.repositories.jobs_relational import JobFullProfile
from app.services.scoring.scoring_prompt_builder import (
    PROTECTED_FIELDS,
    anonymize_candidate,
    anonymize_job,
    build_messages,
)


# ── Lightweight fakes ────────────────────────────────────────────────────


@dataclass
class _FakeCandidate:
    id: object
    full_name: str = "Jane Doe"
    email: str = "jane@example.com"
    phone: str = "+1 555 1212"
    headline: str = "Senior Backend Engineer"
    current_title: str = "Backend Engineer"
    location_text: str = "Cairo, Egypt"
    summary: str = "Built APIs in Python and FastAPI for 5 years."
    years_experience: int = 5
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


@dataclass
class _FakeSkill:
    id: object
    normalized_name: str
    category: str | None = "programming"


@dataclass
class _FakeCandidateSkill:
    id: object
    proficiency_score: int | None = 85
    years_used: int | None = 4
    evidence_text: str | None = "Built REST services"


@dataclass
class _FakeExperience:
    id: object
    title: str = "Senior Engineer"
    company_name: str = "ACME"
    start_date: str | None = "2021-01-01"
    end_date: str | None = "2023-06-01"
    description: str | None = "Backend services."


@dataclass
class _FakeJob:
    id: object
    title: str = "Backend Engineer"
    title_normalized: str | None = "backend engineer"
    company_name: str | None = "Globex"
    summary: str | None = "Build microservices."
    description_text: str | None = "Python + FastAPI + AWS."
    requirements: str | None = "5+ years backend"
    seniority_level: str | None = "senior"
    experience_level: str | None = "5+"
    employment_type: str | None = "full_time"
    workplace_type: str | None = "hybrid"
    location_mode: str = "hybrid"
    location_text: str | None = "Cairo"
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    min_years_experience: int | None = 5
    max_years_experience: int | None = 7
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


@dataclass
class _FakeJobSkill:
    skill_name_raw: str
    skill_name_normalized: str
    is_required: bool = True
    importance_weight: float = 1.0


@dataclass
class _FakeCompany:
    id: object
    name: str
    normalized_name: str = ""


def _profile():
    cand_id = uuid4()
    profile = CandidateFullProfile(candidate=_FakeCandidate(id=cand_id))
    profile.skills = [
        (_FakeCandidateSkill(id=uuid4()), _FakeSkill(id=uuid4(), normalized_name="python")),
        (_FakeCandidateSkill(id=uuid4()), _FakeSkill(id=uuid4(), normalized_name="fastapi")),
    ]
    profile.experiences = [(_FakeExperience(id=uuid4()), None)]
    return profile, cand_id


def _job_profile():
    jid = uuid4()
    job = _FakeJob(id=jid)
    profile = JobFullProfile(job=job)
    profile.company = _FakeCompany(id=uuid4(), name="Globex", normalized_name="globex")
    profile.skill_requirements = [
        (_FakeJobSkill("Python", "python", is_required=True), None),
        (_FakeJobSkill("AWS", "aws", is_required=False, importance_weight=0.5), None),
    ]
    return profile, jid


# ── Tests ──────────────────────────────────────────────────────────────


def test_anonymize_candidate_removes_protected_attributes():
    profile, cand_id = _profile()
    anon = anonymize_candidate(profile, candidate_id=str(cand_id))
    for field_name in {"full_name", "email", "phone", "name", "photo"}:
        assert field_name not in anon
    # Skills, experience, education etc. are preserved
    assert anon["candidate_ref"] == str(cand_id)
    assert anon["years_of_experience"] == 5
    assert any(s["name"] == "python" for s in anon["skills"])


def test_anonymize_job_includes_required_and_preferred_skills():
    profile, jid = _job_profile()
    anon = anonymize_job(profile, job_id=str(jid))
    assert anon["job_ref"] == str(jid)
    assert anon["title"] == "Backend Engineer"
    assert anon["company"] == "Globex"
    assert anon["required_skills"] == ["python"]
    assert anon["preferred_skills"] == ["aws"]


def test_build_messages_payload_does_not_contain_protected_data():
    cand_profile, _ = _profile()
    job_profile, _ = _job_profile()
    anon_cand = anonymize_candidate(cand_profile)
    anon_job = anonymize_job(job_profile)
    messages = build_messages(anon_cand, anon_job)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    blob = json.dumps(messages)
    for protected in {"Jane Doe", "jane@example.com", "+1 555 1212"}:
        assert protected not in blob, (
            f"protected attribute leaked into prompt: {protected}"
        )
    # Required outputs must be requested
    assert "agent_score" in messages[1]["content"]
    assert "criteria_breakdown" in messages[1]["content"]
    assert "JSON ONLY" in messages[1]["content"].upper().replace("ONLY", "ONLY")


def test_protected_fields_set_includes_critical_attributes():
    must_be_protected = {
        "full_name", "email", "phone", "photo", "image", "gender",
        "age", "religion", "nationality", "address", "marital_status",
    }
    assert must_be_protected.issubset(PROTECTED_FIELDS)
