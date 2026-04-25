"""Tests for the vector similarity service.

Pure-Python tests — Qdrant calls are monkey-patched.
"""

from __future__ import annotations

from app.services.scoring.vector_similarity_service import (
    cosine_similarity,
    normalize_to_score,
    compute_similarity_score,
)


def test_cosine_identical_vectors_returns_one():
    assert cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0


def test_cosine_opposite_vectors_returns_minus_one():
    assert cosine_similarity([1, 0, 0], [-1, 0, 0]) == -1.0


def test_cosine_orthogonal_vectors_returns_zero():
    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0


def test_cosine_zero_vector_returns_zero():
    assert cosine_similarity([0, 0, 0], [1, 1, 1]) == 0.0


def test_cosine_dimension_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        cosine_similarity([1, 0], [1, 0, 0])


def test_normalize_maps_minus_one_to_zero():
    assert normalize_to_score(-1.0) == 0.0


def test_normalize_maps_one_to_hundred():
    assert normalize_to_score(1.0) == 100.0


def test_normalize_maps_zero_to_fifty():
    assert normalize_to_score(0.0) == 50.0


def test_compute_similarity_score_returns_zero_when_candidate_missing(monkeypatch):
    from app.services.scoring import vector_similarity_service as svc

    def _fake_retrieve(self, *, collection, point_id):
        if collection == svc.settings.qdrant_candidate_collection:
            return None
        return [1.0, 0.0, 0.0]

    monkeypatch.setattr(
        svc, "_retrieve_vector",
        lambda client, *, collection, point_id: _fake_retrieve(
            None, collection=collection, point_id=point_id,
        ),
    )

    class _FakeClient:
        pass

    monkeypatch.setattr(svc, "_client", lambda: _FakeClient())
    result = compute_similarity_score("c1", "j1")
    assert result.score == 0.0
    assert result.cosine is None
    assert result.candidate_vector_present is False
    assert result.job_vector_present is True
    assert result.status == "completed_with_vector_missing"


def test_compute_similarity_score_full_path(monkeypatch):
    """Both vectors present and identical → score 100."""
    from app.services.scoring import vector_similarity_service as svc

    monkeypatch.setattr(
        svc, "_retrieve_vector",
        lambda client, *, collection, point_id: [1.0, 0.0, 0.0],
    )

    class _FakeClient:
        pass

    monkeypatch.setattr(svc, "_client", lambda: _FakeClient())
    result = compute_similarity_score("c1", "j1")
    assert result.score == 100.0
    assert result.cosine == 1.0
    assert result.status == "ok"
