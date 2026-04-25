"""Unit tests for the deterministic skill dictionary."""

from app.services.job_scraper.skill_dictionary import (
    extract_skills_from_text,
    normalize_skill,
    normalize_skill_list,
)


def test_normalize_skill_canonicalizes_aliases():
    assert normalize_skill("python") == "Python"
    assert normalize_skill("Postgres") == "PostgreSQL"
    assert normalize_skill("react.js") == "React"
    assert normalize_skill("k8s") == "Kubernetes"
    assert normalize_skill("LLM") == "LLM"


def test_normalize_skill_returns_none_for_unknown():
    assert normalize_skill("something_made_up") is None
    assert normalize_skill("") is None


def test_normalize_skill_list_dedupes_and_canonicalizes():
    out = normalize_skill_list(["python", "PYTHON", "py3", "FastAPI", "fastapi"])
    assert out == ["Python", "FastAPI"]


def test_extract_skills_from_text_finds_known_skills():
    text = (
        "We need a backend engineer with strong Python and FastAPI skills. "
        "Bonus for AWS, Docker, and PostgreSQL experience."
    )
    skills = extract_skills_from_text(text)
    assert "Python" in skills
    assert "FastAPI" in skills
    assert "AWS" in skills
    assert "Docker" in skills
    assert "PostgreSQL" in skills


def test_extract_skills_prefers_longest_alias():
    """`react native` must beat `react`."""
    skills = extract_skills_from_text("Looking for React Native developer.")
    assert "React Native" in skills
    assert "React" not in skills


def test_extract_skills_dedupes_repeated_mentions():
    skills = extract_skills_from_text("Python python Python.")
    assert skills == ["Python"]


def test_extract_skills_handles_empty_input():
    assert extract_skills_from_text("") == []
    assert extract_skills_from_text(None) == []  # type: ignore[arg-type]
