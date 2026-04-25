"""Tests for the relevance filter — ensures we never score irrelevant pairs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.db.repositories.candidates_relational import CandidateFullProfile
from app.db.repositories.jobs_relational import JobFullProfile
from app.services.scoring.relevance_filter_service import (
    assess_relevance,
    candidate_role_family,
    infer_role_family,
    job_required_skills,
    job_role_family,
    skill_overlap_ratio,
)


# ── Lightweight fakes mirroring the SQLAlchemy models ──────────────────


@dataclass
class _C:
    id: object
    headline: str | None = None
    current_title: str | None = None
    location_text: str | None = None
    summary: str | None = None
    years_experience: int | None = 5
    full_name: str = "Anon"
    email: str | None = None
    phone: str | None = None
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


@dataclass
class _CS:
    id: object = None
    proficiency_score: int | None = None
    years_used: int | None = None
    evidence_text: str | None = None


@dataclass
class _Sk:
    id: object
    normalized_name: str
    category: str | None = None


@dataclass
class _Exp:
    id: object
    title: str
    company_name: str = "ACME"
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


@dataclass
class _Job:
    id: object
    title: str
    title_normalized: str | None = None
    company_name: str | None = "Globex"
    summary: str | None = None
    description_text: str | None = None
    requirements: str | None = None
    seniority_level: str | None = None
    experience_level: str | None = None
    employment_type: str = "full_time"
    workplace_type: str | None = None
    location_mode: str = "hybrid"
    location_text: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    min_years_experience: int | None = None
    max_years_experience: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


@dataclass
class _JSR:
    skill_name_raw: str
    skill_name_normalized: str
    is_required: bool = True
    importance_weight: float = 1.0


def _candidate(*skills: str, title: str = "Senior Backend Engineer") -> CandidateFullProfile:
    profile = CandidateFullProfile(
        candidate=_C(id=uuid4(), current_title=title, headline=title),
    )
    profile.skills = [
        (_CS(), _Sk(id=uuid4(), normalized_name=s)) for s in skills
    ]
    profile.experiences = [(_Exp(id=uuid4(), title=title), None)]
    return profile


def _job(
    title: str,
    *,
    required: list[str] | None = None,
    preferred: list[str] | None = None,
    description: str | None = None,
) -> JobFullProfile:
    job = _Job(id=uuid4(), title=title, description_text=description)
    profile = JobFullProfile(job=job)
    reqs: list = []
    for s in required or []:
        reqs.append((_JSR(s, s.lower(), is_required=True), None))
    for s in preferred or []:
        reqs.append((_JSR(s, s.lower(), is_required=False), None))
    profile.skill_requirements = reqs
    return profile


# ── Helpers ────────────────────────────────────────────────────────────


def test_infer_role_family_software():
    assert infer_role_family("python fastapi backend developer rest") == "software_engineering"


def test_infer_role_family_finance():
    assert infer_role_family("accountant tax accountant audit") == "finance"


def test_infer_role_family_machine_learning():
    assert infer_role_family("ml engineer pytorch deep learning") == "machine_learning"


def test_infer_role_family_other_for_unknown():
    assert infer_role_family("plumber drywall installer") == "other"


def test_candidate_role_family_picks_software():
    profile = _candidate("python", "fastapi", "postgresql")
    assert candidate_role_family(profile) == "software_engineering"


def test_job_role_family_picks_finance():
    profile = _job("Accountant", required=["excel"], description="audit and tax accountant")
    assert job_role_family(profile) == "finance"


def test_skill_overlap_basic():
    cand = {"python", "fastapi", "aws"}
    overlap = skill_overlap_ratio(cand, ["python", "fastapi", "kubernetes"])
    assert overlap == 2 / 3


def test_skill_overlap_empty_required():
    assert skill_overlap_ratio({"python"}, []) == 0.0


def test_job_required_skills_partition():
    profile = _job("X", required=["python"], preferred=["aws", "docker"])
    required, preferred = job_required_skills(profile)
    assert required == {"python"}
    assert preferred == {"aws", "docker"}


# ── assess_relevance ───────────────────────────────────────────────────


def test_software_candidate_matches_backend_job():
    cand = _candidate("python", "fastapi", "postgresql")
    job = _job("Backend Engineer", required=["python", "fastapi"])
    decision = assess_relevance(cand, job, vector_similarity_score=70.0)
    assert decision.is_relevant is True
    assert decision.candidate_role_family == "software_engineering"
    assert decision.job_role_family == "software_engineering"
    assert decision.skill_overlap_ratio == 1.0


def test_software_candidate_does_not_match_accountant_job():
    cand = _candidate("python", "fastapi", "postgresql")
    job = _job(
        "Accountant",
        required=["excel", "audit"],
        description="audit tax accountant accounting",
    )
    decision = assess_relevance(cand, job, vector_similarity_score=10.0)
    assert decision.is_relevant is False
    assert decision.candidate_role_family == "software_engineering"
    assert decision.job_role_family == "finance"


def test_data_scientist_candidate_matches_ml_job():
    cand = _candidate("pytorch", "pandas", "tensorflow")
    cand.candidate.current_title = "Data Scientist"
    cand.candidate.headline = "Senior Data Scientist with ML focus"
    job = _job(
        "Machine Learning Engineer",
        required=["pytorch", "ml"],
        description="ml engineer pytorch deep learning",
    )
    decision = assess_relevance(cand, job, vector_similarity_score=82.0)
    assert decision.is_relevant is True
    assert decision.job_role_family in {"machine_learning", "data_science"}


def test_strong_vector_alone_can_make_adjacent_relevant():
    """Software → DevOps adjacency, vector similarity above threshold."""
    cand = _candidate("python")
    cand.candidate.current_title = "Backend Developer"
    job = _job("Site Reliability Engineer", required=["kubernetes"])
    decision = assess_relevance(cand, job, vector_similarity_score=88.0)
    assert decision.is_relevant is True


def test_incompatible_pair_blocked_without_strong_evidence():
    cand = _candidate("python", "fastapi")
    job = _job("HR Specialist", required=["recruiting"], description="human resources hr business partner")
    decision = assess_relevance(cand, job, vector_similarity_score=20.0)
    assert decision.is_relevant is False
    assert any("incompatible" in r for r in decision.reasons)
