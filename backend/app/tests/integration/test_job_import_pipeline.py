"""End-to-end test for the hourly Job_Scraper-main → PG → AGE → Qdrant pipeline.

Skipped automatically when the required services are not reachable so it
is safe to run in CI without infrastructure. The test forces stub mode
on the scraper adapter and instead injects 3 fabricated raw jobs to
exercise the import service end-to-end.

To run:
    docker compose up -d postgres qdrant
    alembic upgrade head
    pytest app/tests/integration/test_job_import_pipeline.py -v
"""

from __future__ import annotations

import asyncio
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


def _fake_raw_jobs() -> list[dict]:
    nonce = uuid.uuid4().hex[:8]
    return [
        {
            "company_name": f"Integration Co {nonce}",
            "job_title": "Senior Backend Engineer",
            "job_url": f"https://example.com/integration/{nonce}/1",
            "job_location": "Remote, EU",
            "job_description": "Build APIs in Python and FastAPI on AWS.",
            "platform": "Lever",
            "source_platform": "linkedin",
        },
        {
            "company_name": f"Integration Co {nonce}",
            "job_title": "Data Engineer",
            "job_url": f"https://example.com/integration/{nonce}/2",
            "job_location": "Hybrid",
            "job_description": "PostgreSQL, Airflow and Python skills.",
            "platform": "Lever",
            "source_platform": "linkedin",
        },
    ]


def test_import_service_runs_end_to_end_with_fake_adapter(db):
    """Run the full import pipeline against live PostgreSQL + Qdrant."""
    from unittest.mock import AsyncMock

    from app.services.job_scraper.job_import_service import JobImportService
    from app.services.job_scraper.scraper_adapter import (
        JobScraperAdapter,
        ScrapeRunResult,
    )

    adapter = JobScraperAdapter(stub=True)
    raw = _fake_raw_jobs()
    fake_run = ScrapeRunResult(raw_jobs=raw, companies_visited=1, new_offset=1)
    adapter.scrape_jobs = AsyncMock(return_value=fake_run)  # type: ignore[method-assign]

    service = JobImportService(adapter=adapter)
    result = asyncio.run(service.run_import(limit=5, source="linkedin"))

    assert result.scraped_count == len(raw)
    assert result.valid_count == len(raw)
    assert result.inserted_count + result.updated_count == len(raw)
    assert result.status in {"success", "partial"}

    from app.db.repositories import jobs_vector
    for jid in result.job_ids:
        verify = jobs_vector.verify_one_vector_per_job(jid)
        assert verify["exists"] is True
        assert verify["payload_job_id"] == jid
        assert verify["vector_count_for_job"] == 1
        with suppress(Exception):
            jobs_vector.delete_candidate_vector  # noqa: B018  (sanity check)
            jobs_vector.delete_job_vector(jid)
