"""Tests for the unified ID contract.

Validates that the spec-required identifiers are stable, equal across
stores, and that the verification helpers correctly detect ID drift.

These tests do not require a live database — they exercise the
shape/logic of the verification responses with monkey-patched
repositories.
"""

from uuid import uuid4

import pytest


def test_candidate_verification_marks_unified_id_invalid_when_qdrant_id_differs(
    monkeypatch,
):
    cid = str(uuid4())
    other = str(uuid4())

    fake_point = {
        "id": other,  # WRONG — different from candidate_id
        "payload": {"candidate_id": other, "source_hash": "h", "embedding_model": "m"},
    }

    from app.db.repositories import candidates_vector

    monkeypatch.setattr(
        candidates_vector, "get_candidate_point", lambda _id: fake_point,
    )

    class _FakeClient:
        def count(self, collection_name, count_filter, exact):
            class _R:
                count = 1
            return _R()
    monkeypatch.setattr(candidates_vector, "_client", lambda: _FakeClient())

    result = candidates_vector.verify_one_vector_per_candidate(cid)
    assert result["candidate_id"] == cid
    assert result["unified_id_valid"] is False
    assert result["payload_candidate_id"] == other


def test_candidate_verification_passes_when_ids_align(monkeypatch):
    cid = str(uuid4())
    fake_point = {
        "id": cid,
        "payload": {
            "candidate_id": cid, "source_hash": "h", "embedding_model": "m",
        },
    }

    from app.db.repositories import candidates_vector

    monkeypatch.setattr(
        candidates_vector, "get_candidate_point", lambda _id: fake_point,
    )

    class _FakeClient:
        def count(self, collection_name, count_filter, exact):
            class _R:
                count = 1
            return _R()
    monkeypatch.setattr(candidates_vector, "_client", lambda: _FakeClient())

    result = candidates_vector.verify_one_vector_per_candidate(cid)
    assert result["unified_id_valid"] is True
    assert result["vector_count_for_candidate"] == 1
    assert result["point_id"] == cid


def test_job_verification_one_vector_rule_fails_for_two_points(monkeypatch):
    jid = str(uuid4())
    fake_point = {
        "id": jid,
        "payload": {"job_id": jid, "source_hash": "h", "embedding_model": "m"},
    }

    from app.db.repositories import jobs_vector

    monkeypatch.setattr(
        jobs_vector, "get_job_point", lambda _id: fake_point,
    )

    class _FakeClient:
        def count(self, collection_name, count_filter, exact):
            class _R:
                count = 2  # SPEC VIOLATION — two vectors for one job
            return _R()
    monkeypatch.setattr(jobs_vector, "_client", lambda: _FakeClient())

    result = jobs_vector.verify_one_vector_per_job(jid)
    assert result["vector_count_for_job"] == 2
    assert result["unified_id_valid"] is False


def test_job_verification_passes_when_one_vector_only(monkeypatch):
    jid = str(uuid4())
    fake_point = {
        "id": jid,
        "payload": {"job_id": jid, "source_hash": "h", "embedding_model": "m"},
    }

    from app.db.repositories import jobs_vector

    monkeypatch.setattr(jobs_vector, "get_job_point", lambda _id: fake_point)

    class _FakeClient:
        def count(self, collection_name, count_filter, exact):
            class _R:
                count = 1
            return _R()
    monkeypatch.setattr(jobs_vector, "_client", lambda: _FakeClient())

    result = jobs_vector.verify_one_vector_per_job(jid)
    assert result["unified_id_valid"] is True
    assert result["vector_count_for_job"] == 1
