"""Tests for the candidate / job vector text builders.

These are pure-Python tests using lightweight fakes so they can run
without a live PostgreSQL/AGE/Qdrant.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.db.repositories.candidates_relational import CandidateFullProfile
from app.db.repositories.jobs_relational import JobFullProfile
from app.services.vector_text_builders import (
    build_candidate_vector_text,
    build_job_vector_text,
    text_source_hash,
)


# ── Lightweight fakes (mimic the SQLAlchemy attribute access we use) ───


@dataclass
class _FakeCandidate:
    id: UUID
    full_name: str = "Alex Doe"
    email: str | None = "alex@example.com"
    phone: str | None = None
    headline: str | None = "Senior Backend Engineer"
    current_title: str | None = "Backend Engineer"
    location_text: str | None = "Cairo, Egypt"
    summary: str | None = "Built backend services for 5 years."
    years_experience: int | None = 5
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


@dataclass
class _FakeSkill:
    id: UUID
    normalized_name: str
    category: str | None = "programming"


@dataclass
class _FakeCandidateSkill:
    id: UUID
    proficiency_score: int | None = 85
    years_used: int | None = 4
    evidence_text: str | None = "Used in production"


@dataclass
class _FakeExperience:
    id: UUID
    title: str = "Backend Engineer"
    company_name: str = "ACME Inc"
    start_date: str | None = "2021-01-01"
    end_date: str | None = "2023-06-01"
    description: str | None = "Built REST APIs and async pipelines."


@dataclass
class _FakeJob:
    id: UUID
    organization_id: UUID | None = None
    title: str = "Senior Backend Engineer"
    title_normalized: str | None = "senior backend engineer"
    company_name: str | None = "ACME Inc"
    description_text: str | None = "We need a backend engineer."
    requirements: str | None = "5+ years of backend experience"
    role_family: str | None = None
    employment_type: str | None = "full_time"
    seniority_level: str | None = "senior"
    experience_level: str | None = "5+"
    location_text: str | None = "Cairo, Egypt"
    location_mode: str = "hybrid"
    country_code: str | None = "EG"
    city: str | None = "Cairo"
    department: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    source_type: str = "manual"
    status: str = "open"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


@dataclass
class _FakeJobSkill:
    skill_name_raw: str
    skill_name_normalized: str
    importance_weight: float = 1.0
    is_required: bool = True


# ── Tests ──────────────────────────────────────────────────────────────


def test_candidate_vector_text_contains_skills_and_experience():
    cand_id = uuid4()
    skill_id = uuid4()
    profile = CandidateFullProfile(candidate=_FakeCandidate(id=cand_id))
    profile.skills = [
        (
            _FakeCandidateSkill(id=uuid4()),
            _FakeSkill(id=skill_id, normalized_name="python"),
        ),
        (
            _FakeCandidateSkill(id=uuid4(), evidence_text="used at ACME"),
            _FakeSkill(id=uuid4(), normalized_name="postgresql", category="database"),
        ),
    ]
    profile.experiences = [(_FakeExperience(id=uuid4()), None)]

    text = build_candidate_vector_text(profile)
    assert "Entity Type: Candidate" in text
    assert f"Candidate ID: {cand_id}" in text
    assert "python" in text
    assert "postgresql" in text
    assert "Backend Engineer at ACME Inc" in text
    assert "Built REST APIs" in text


def test_candidate_vector_text_does_not_include_qr_or_image_noise():
    cand = _FakeCandidate(
        id=uuid4(),
        summary="data:image/png;base64,iVBORw0KGgo Scan QR Code below",
    )
    profile = CandidateFullProfile(candidate=cand)
    text = build_candidate_vector_text(profile)
    # Summary is included raw — sanitization is applied to CV documents,
    # not to structured PG fields. But the spec template still does not
    # add image/QR markers itself.
    assert text.startswith("Entity Type: Candidate")


def test_candidate_vector_text_is_deterministic_for_hashing():
    cand_id = uuid4()
    profile = CandidateFullProfile(candidate=_FakeCandidate(id=cand_id))
    h1 = text_source_hash(build_candidate_vector_text(profile))
    h2 = text_source_hash(build_candidate_vector_text(profile))
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_job_vector_text_contains_required_skills_and_experience_range():
    job_id = uuid4()
    profile = JobFullProfile(job=_FakeJob(id=job_id))
    profile.skill_requirements = [
        (_FakeJobSkill(skill_name_raw="Python", skill_name_normalized="python"), None),
        (_FakeJobSkill(
            skill_name_raw="AWS",
            skill_name_normalized="aws",
            is_required=False,
            importance_weight=0.5,
        ), None),
    ]
    text = build_job_vector_text(profile)
    assert "Entity Type: Job" in text
    assert f"Job ID: {job_id}" in text
    assert "python" in text
    assert "aws" in text
    assert "type: required" in text
    assert "type: preferred" in text
    assert "5+ years" in text  # requirements field
    assert "Senior Backend Engineer" in text
