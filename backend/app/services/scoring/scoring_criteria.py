"""
PATHS Backend — Default scoring criteria.

The agent score returned by the LlamaAgent must be the sum of these six
component scores. Total = 100. Weights are configurable through the
optional `scoring_criteria` table (see `db/models/scoring.py`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringCriterion:
    key: str            # JSON key returned by the agent
    label: str          # human-readable label (used in the prompt)
    description: str
    max_score: int      # max points for this criterion (0..max_score)


DEFAULT_CRITERIA: tuple[ScoringCriterion, ...] = (
    ScoringCriterion(
        key="skills_match",
        label="Skills Match",
        description="Required and preferred skills overlap.",
        max_score=35,
    ),
    ScoringCriterion(
        key="experience_match",
        label="Experience Match",
        description=(
            "Years of experience, previous roles, seniority, and role history."
        ),
        max_score=20,
    ),
    ScoringCriterion(
        key="project_domain_match",
        label="Project / Domain Match",
        description=(
            "Candidate projects, previous domains, tools, and practical work "
            "relevance."
        ),
        max_score=15,
    ),
    ScoringCriterion(
        key="education_certifications",
        label="Education / Certifications",
        description=(
            "Degree, certifications, courses, and academic background if relevant."
        ),
        max_score=10,
    ),
    ScoringCriterion(
        key="job_preferences_fit",
        label="Job Preferences Fit",
        description=(
            "Location, remote/hybrid/onsite preference, employment type, "
            "salary if available."
        ),
        max_score=10,
    ),
    ScoringCriterion(
        key="growth_potential",
        label="Growth Potential / Transferable Skills",
        description=(
            "Ability to learn missing tools based on related skills and background."
        ),
        max_score=10,
    ),
)


TOTAL_MAX_SCORE: int = sum(c.max_score for c in DEFAULT_CRITERIA)
assert TOTAL_MAX_SCORE == 100, "default criteria must sum to 100"


def criteria_keys() -> list[str]:
    return [c.key for c in DEFAULT_CRITERIA]


def empty_criteria_payload() -> dict[str, dict[str, int | str]]:
    """Return a zero-filled `criteria_breakdown` skeleton (used for fallback)."""
    return {
        c.key: {"score": 0, "max_score": c.max_score, "reason": ""}
        for c in DEFAULT_CRITERIA
    }


# ── Final-score classification (per spec) ────────────────────────────────


def classify_final_score(final_score: float) -> str:
    """Map 0–100 → human-readable match label."""
    if final_score >= 90:
        return "Excellent Match"
    if final_score >= 75:
        return "Strong Match"
    if final_score >= 60:
        return "Good Match"
    if final_score >= 45:
        return "Possible Match"
    return "Weak Match"


def recommendation_for(final_score: float) -> str:
    """Return the spec-defined `recommendation` enum string for a final score."""
    if final_score >= 75:
        return "strong_match"
    if final_score >= 60:
        return "good_match"
    if final_score >= 45:
        return "possible_match"
    if final_score >= 25:
        return "weak_match"
    return "not_recommended"


__all__ = [
    "ScoringCriterion",
    "DEFAULT_CRITERIA",
    "TOTAL_MAX_SCORE",
    "criteria_keys",
    "empty_criteria_payload",
    "classify_final_score",
    "recommendation_for",
]
