"""Tests for the final-score combination + ScoringService helpers."""

from __future__ import annotations

from app.services.scoring.scoring_service import combine_scores


def test_combine_default_weights_matches_spec_example():
    # Spec example: agent=80, vector=90 → 80*0.65 + 90*0.35 = 83.5
    assert combine_scores(80, 90) == 83.5


def test_combine_renormalizes_when_weights_dont_sum_to_one():
    # Misconfigured: 0.5 + 0.5 → renormalized → 0.5/1.0 each
    assert combine_scores(80, 90, agent_weight=0.5, vector_weight=0.5) == 85.0


def test_combine_clamps_to_zero_hundred():
    assert combine_scores(0, 0) == 0.0
    assert combine_scores(100, 100) == 100.0


def test_combine_falls_back_to_default_when_weights_invalid():
    # Negative weights → fall back to default 0.65/0.35
    assert combine_scores(80, 90, agent_weight=-1.0, vector_weight=-1.0) == 83.5
