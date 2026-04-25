"""Tests for the default scoring criteria + classification helpers."""

from app.services.scoring.scoring_criteria import (
    DEFAULT_CRITERIA,
    TOTAL_MAX_SCORE,
    classify_final_score,
    criteria_keys,
    empty_criteria_payload,
    recommendation_for,
)


def test_default_criteria_sums_to_100():
    assert TOTAL_MAX_SCORE == 100
    assert sum(c.max_score for c in DEFAULT_CRITERIA) == 100


def test_criteria_keys_match_spec_layout():
    keys = criteria_keys()
    assert keys == [
        "skills_match",
        "experience_match",
        "project_domain_match",
        "education_certifications",
        "job_preferences_fit",
        "growth_potential",
    ]


def test_empty_payload_has_max_score_for_each_criterion():
    payload = empty_criteria_payload()
    for c in DEFAULT_CRITERIA:
        assert payload[c.key]["max_score"] == c.max_score
        assert payload[c.key]["score"] == 0


def test_classify_final_score_buckets():
    assert classify_final_score(95) == "Excellent Match"
    assert classify_final_score(80) == "Strong Match"
    assert classify_final_score(65) == "Good Match"
    assert classify_final_score(50) == "Possible Match"
    assert classify_final_score(20) == "Weak Match"


def test_recommendation_for_buckets():
    assert recommendation_for(90) == "strong_match"
    assert recommendation_for(75) == "strong_match"
    assert recommendation_for(60) == "good_match"
    assert recommendation_for(50) == "possible_match"
    assert recommendation_for(30) == "weak_match"
    assert recommendation_for(10) == "not_recommended"
