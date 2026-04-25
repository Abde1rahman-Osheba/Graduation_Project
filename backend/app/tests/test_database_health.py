"""Smoke tests for the database health service.

We monkey-patch the engine and Qdrant client to verify the response
shape matches the spec exactly:

    {"postgres": {...}, "apache_age": {...}, "qdrant": {...}}

The actual DB connectivity is exercised by the integration test suite.
"""

from contextlib import contextmanager

import pytest


@contextmanager
def _fake_engine_connect(values):
    """Fake the SQLAlchemy connect/execute interface."""
    class _Conn:
        def __init__(self, vals):
            self._values = vals

        def execute(self, *_args, **_kwargs):
            class _R:
                def scalar(self_inner):
                    return self._values.pop(0) if self._values else None

                def first(self_inner):
                    return (1,) if self._values else None

            return _R()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    yield _Conn(values)


def test_health_payload_shape_is_spec_compliant(monkeypatch):
    from app.services import database_health_service as svc

    @contextmanager
    def fake_connect():
        with _fake_engine_connect([1, "paths_db", "1.5.0", 1]) as c:
            yield c

    monkeypatch.setattr(svc.engine, "connect", lambda: fake_connect())

    class _FakeQdrantClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_collections(self):
            class _R:
                pass
            r = _R()
            class _C:
                pass
            cand = _C()
            cand.name = svc.settings.qdrant_candidate_collection
            job = _C()
            job.name = svc.settings.qdrant_job_collection
            r.collections = [cand, job]
            return r

    monkeypatch.setattr(svc, "QdrantClient", _FakeQdrantClient)

    result = svc.check_all()
    assert set(result.keys()) == {"postgres", "apache_age", "qdrant"}
    assert "details" in result["postgres"]
    assert "graph" in result["apache_age"]
    assert "candidate_collection" in result["qdrant"]
    assert "job_collection" in result["qdrant"]
    # Both collections present → connected
    assert result["qdrant"]["status"] == "connected"


def test_health_payload_marks_qdrant_degraded_when_collections_missing(monkeypatch):
    from app.services import database_health_service as svc

    @contextmanager
    def fake_connect():
        with _fake_engine_connect([1, "paths_db", "1.5.0", 1]) as c:
            yield c

    monkeypatch.setattr(svc.engine, "connect", lambda: fake_connect())

    class _FakeQdrantClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_collections(self):
            class _R:
                collections = []
            return _R()

    monkeypatch.setattr(svc, "QdrantClient", _FakeQdrantClient)

    result = svc.check_all()
    assert result["qdrant"]["status"] == "degraded"
    assert "missing" in result["qdrant"]["details"]


def test_safe_error_redacts_password(monkeypatch):
    from app.services import database_health_service as svc

    monkeypatch.setattr(svc.settings, "postgres_password", "MYSECRET", raising=False)
    msg = svc._safe_error(Exception("connection refused: password=MYSECRET"))
    assert "MYSECRET" not in msg
    assert "***" in msg
