"""
PATHS Backend — FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    setup_logging()
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)

    # Hourly job-scraper scheduler — opt-in via JOB_SCRAPER_ENABLED=true.
    # Importing inside the lifespan keeps APScheduler optional.
    from app.services.job_scraper.scheduler import scheduler as job_scheduler
    try:
        await job_scheduler.start()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to start hourly job-scraper scheduler")

    try:
        yield
    finally:
        try:
            await job_scheduler.shutdown()
        except Exception:  # noqa: BLE001
            logger.exception("Error while shutting down job-scraper scheduler")
        logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="PATHS — Hiring workflow backend with PostgreSQL, Apache AGE, and Qdrant",
    lifespan=lifespan,
)

# ── Import routers ─────────────────────────────────────────────────────
from app.api.v1.health import router as health_router  # noqa: E402
from app.api.v1.system import router as system_router  # noqa: E402
from app.api.v1.cv_ingestion import router as cv_ingestion_router  # noqa: E402
from app.api.v1.candidates import router as candidates_router  # noqa: E402
from app.api.v1.auth import router as auth_router  # noqa: E402
from app.api.v1.organizations import router as organizations_router  # noqa: E402
from app.api.v1.job_ingestion import router as job_ingestion_router  # noqa: E402
from app.api.v1.admin import router as admin_router  # noqa: E402
from app.api.v1.job_import import router as job_import_router  # noqa: E402
from app.api.v1.scoring import router as scoring_router  # noqa: E402
from app.api.v1.organization_matching import (  # noqa: E402
    router as organization_matching_router,
)

# ── Register routers ───────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1")
app.include_router(organizations_router, prefix="/api/v1")
app.include_router(cv_ingestion_router, prefix="/api/v1")
app.include_router(candidates_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
app.include_router(job_ingestion_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(job_import_router, prefix="/api/v1")
app.include_router(scoring_router, prefix="/api/v1")
app.include_router(organization_matching_router, prefix="/api/v1")
# Health router exposes /api/v1/health/databases plus the legacy
# per-service paths used by integration tests.
app.include_router(health_router, prefix="/api/v1")


# ── Root-level health endpoint (legacy - kept for backward compatibility) ──
@app.get("/health", tags=["Health"])
def root_health():
    """Root-level aggregated health check returning per-service connectivity."""
    import os
    import httpx
    from app.services.postgres_service import PostgresService
    from app.services.age_service import AGEService
    from app.services.qdrant_service import QdrantService

    pg = PostgresService.test_connection()
    age = AGEService.test_connection()

    qdrant_svc = QdrantService()
    qd = qdrant_svc.test_connection()

    base_url = settings.ollama_base_url
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=3.0)
        ol = {"status": "healthy" if r.status_code == 200 else "unhealthy"}
    except Exception:
        ol = {"status": "unreachable"}

    return {
        "postgres": pg,
        "age": age,
        "qdrant": qd,
        "ollama": ol,
    }


# ── Spec-compliant root-level GET /health/databases ────────────────────
# 01_MASTER_DATABASE_INTEGRATION_INSTRUCTIONS.md (Phase 2) requires this
# exact path with the canonical {postgres, apache_age, qdrant} payload.
@app.get("/health/databases", tags=["Health"])
def health_databases_root():
    from app.services.database_health_service import check_all
    return check_all()


@app.get("/", tags=["Root"])
def root():
    """Root endpoint."""
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
    }
