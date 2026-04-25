"""Unit tests for the job-scraper normalizer."""

from __future__ import annotations

from app.services.job_scraper.job_normalizer import (
    NormalizedJob,
    detect_employment_type,
    detect_experience_range,
    detect_seniority,
    detect_workplace_type,
    normalize_one,
    normalize_scraped_jobs,
    validate_normalized_job,
)


# ── Pure helper functions ────────────────────────────────────────────────


def test_workplace_type_remote():
    assert detect_workplace_type("Senior Backend (Remote)", None) == "remote"
    assert detect_workplace_type(None, "Work-from-home") == "remote"


def test_workplace_type_hybrid_and_onsite():
    assert detect_workplace_type("Hybrid - Cairo") == "hybrid"
    assert detect_workplace_type("Engineer (On-site, NYC)") == "onsite"
    assert detect_workplace_type("Engineer (in office)") == "onsite"


def test_workplace_type_unknown_default():
    assert detect_workplace_type("Backend Engineer") == "unknown"
    assert detect_workplace_type("") == "unknown"


def test_experience_range_three_plus():
    assert detect_experience_range("3+ years experience required") == (3, None)
    assert detect_experience_range("at least 4 years") == (4, None)


def test_experience_range_two_to_five():
    assert detect_experience_range("2-5 years of professional experience") == (2, 5)
    assert detect_experience_range("2 to 4 yrs") == (2, 4)


def test_experience_range_unknown():
    assert detect_experience_range("nice to have", None) == (None, None)


def test_employment_type_detection():
    assert detect_employment_type("Full-Time backend engineer") == "full_time"
    assert detect_employment_type("Part time intern") == "part_time"
    assert detect_employment_type("3-month contract role") == "contract"
    assert detect_employment_type("paid internship") == "internship"
    assert detect_employment_type("just normal text") is None


def test_seniority_detection():
    assert detect_seniority("Senior Backend Engineer") == "senior"
    assert detect_seniority("Junior Data Scientist") == "junior"
    assert detect_seniority("Engineering Manager") == "manager"
    assert detect_seniority("Backend Engineer") is None


# ── normalize_one + validate ─────────────────────────────────────────────


def _raw(**overrides):
    base = {
        "job_title": "Senior Backend Engineer",
        "company_name": "ACME Inc",
        "job_url": "https://example.com/jobs/1",
        "job_location": "Remote, EU",
        "job_description": (
            "We are hiring a Senior Backend Engineer with 3+ years of "
            "Python and FastAPI experience. Bonus for AWS and Docker."
        ),
        "platform": "Lever",
    }
    base.update(overrides)
    return base


def test_normalize_extracts_skills_from_description():
    job = normalize_one(_raw())
    assert job.title == "Senior Backend Engineer"
    assert job.company_name == "ACME Inc"
    assert job.source_platform == "linkedin"
    assert job.workplace_type == "remote"
    assert job.min_years_experience == 3
    assert job.max_years_experience is None
    assert "Python" in job.required_skills
    assert "FastAPI" in job.required_skills
    # Bonus / preferred not handled yet → at minimum AWS & Docker should appear in required
    assert "AWS" in job.required_skills
    assert "Docker" in job.required_skills


def test_normalize_uses_explicit_skill_list_when_provided():
    raw = _raw(
        required_skills=["python", "fastapi"],
        preferred_skills=["docker", "kubernetes"],
    )
    job = normalize_one(raw)
    assert job.required_skills == ["Python", "FastAPI"]
    assert job.preferred_skills == ["Docker", "Kubernetes"]


def test_validate_rejects_missing_title():
    job = normalize_one(_raw(job_title="", title=""))
    ok, reasons = validate_normalized_job(job)
    assert ok is False
    assert "missing_title" in reasons


def test_validate_rejects_missing_company():
    job = normalize_one(_raw(company_name="", company=""))
    ok, reasons = validate_normalized_job(job)
    assert ok is False
    assert "missing_company" in reasons


def test_validate_rejects_missing_source_url():
    job = normalize_one(_raw(job_url="", url=""))
    ok, reasons = validate_normalized_job(job)
    assert ok is False
    assert "missing_source_url" in reasons


def test_normalize_scraped_jobs_splits_valid_and_rejected():
    raw_jobs = [
        _raw(),
        _raw(job_title=""),  # invalid
        _raw(job_url="https://example.com/jobs/2"),
    ]
    valid, rejected = normalize_scraped_jobs(raw_jobs)
    assert len(valid) == 2
    assert len(rejected) == 1
    assert "missing_title" in rejected[0].reasons


def test_normalize_strips_tracking_params_from_url():
    job = normalize_one(_raw(job_url="https://example.com/jobs/1?utm_source=x&utm_medium=y&trk=zzz"))
    assert "utm_" not in job.source_url
    assert "trk" not in job.source_url


def test_normalize_strips_linkedin_boilerplate_from_description():
    raw = _raw(job_description="Easy apply for this role. We need Python skills.")
    job = normalize_one(raw)
    assert job.description and "Easy apply" not in job.description
    assert "Python" in job.required_skills
