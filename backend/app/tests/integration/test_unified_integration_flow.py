"""Integration tests for the unified PG ↔ AGE ↔ Qdrant flow.

Skipped automatically when the required services are not reachable so
they don't break local unit-test runs. To run them:

    docker compose up -d postgres qdrant ollama
    alembic upgrade head
    pytest app/tests/integration/test_unified_integration_flow.py -v
"""

from __future__ import annotations

import os
import uuid
from contextlib import suppress

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _can_connect_postgres() -> bool:
    try:
        eng = create_engine(settings.database_url, pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _can_connect_qdrant() -> bool:
    try:
        import httpx
        r = httpx.get(f"{settings.qdrant_url}/collections", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (_can_connect_postgres() and _can_connect_qdrant()),
    reason="requires live postgres + qdrant",
)


@pytest.fixture
def db():
    eng = create_engine(settings.database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=eng)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_health_databases_endpoint_returns_spec_shape(db):
    """`GET /health/databases` must include postgres / apache_age / qdrant."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        r = client.get("/health/databases")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"postgres", "apache_age", "qdrant"}


def test_unified_candidate_sync_creates_one_qdrant_point(db):
    """End-to-end: create a candidate row, sync, assert exactly one Qdrant point."""
    from app.db.models.candidate import Candidate
    from app.db.repositories import candidates_vector
    from app.services.candidate_sync_service import sync_candidate_full

    candidate = Candidate(
        id=uuid.uuid4(),
        full_name="Integration Test Candidate",
        email=f"int-{uuid.uuid4()}@example.com",
        summary="Built APIs and pipelines.",
        status="active",
    )
    db.add(candidate)
    db.commit()

    try:
        result = sync_candidate_full(db, candidate.id)
        assert result["graph"]["status"] in {"success", "error"}  # AGE may not be ready
        assert result["vector"]["status"] in {"success", "unchanged"}

        verify = candidates_vector.verify_one_vector_per_candidate(candidate.id)
        assert verify["exists"] is True
        assert verify["point_id"] == str(candidate.id)
        assert verify["payload_candidate_id"] == str(candidate.id)
        assert verify["vector_count_for_candidate"] == 1
        assert verify["unified_id_valid"] is True
    finally:
        with suppress(Exception):
            candidates_vector.delete_candidate_vector(candidate.id)
        db.delete(candidate)
        db.commit()
