"""
PATHS Backend — Health-check endpoints.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import FullHealthResponse, HealthResponse, ServiceHealth
from app.services.age_service import AGEService
from app.services.database_health_service import check_all as check_all_databases
from app.services.postgres_service import PostgresService
from app.services.qdrant_service import QdrantService
import httpx
import os

router = APIRouter(prefix="/health", tags=["Health"])
settings = get_settings()


@router.get("/databases")
def health_databases():
    """Spec-compliant aggregated health for postgres / apache_age / qdrant.

    Returns:
        {
          "postgres":   { "status": "connected"|"error", "details": "..." },
          "apache_age": { "status": "connected"|"degraded"|"error",
                          "graph": "paths_graph", "details": "..." },
          "qdrant":     { "status": "connected"|"degraded"|"error",
                          "candidate_collection": "...",
                          "job_collection": "...",
                          "details": "..." }
        }

    See `01_MASTER_DATABASE_INTEGRATION_INSTRUCTIONS.md` (Phase 2).
    """
    return check_all_databases()


@router.get("", response_model=HealthResponse)
def health():
    """Basic liveness probe."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
    )


@router.get("/postgres", response_model=ServiceHealth)
def health_postgres():
    """PostgreSQL connectivity check."""
    result = PostgresService.test_connection()
    return ServiceHealth(service="postgres", status=result["status"], details=result)


@router.get("/age", response_model=ServiceHealth)
def health_age():
    """Apache AGE connectivity check."""
    result = AGEService.test_connection()
    return ServiceHealth(service="age", status=result["status"], details=result)


@router.get("/qdrant", response_model=ServiceHealth)
def health_qdrant():
    """Qdrant connectivity check."""
    svc = QdrantService()
    result = svc.test_connection()
    return ServiceHealth(service="qdrant", status=result["status"], details=result)


@router.get("/all", response_model=FullHealthResponse)
def health_all():
    """Aggregated health check for every backend service."""
    pg = PostgresService.test_connection()
    age = AGEService.test_connection()
    qdrant_svc = QdrantService()
    qd = qdrant_svc.test_connection()
    
    # Ollama health
    base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=3.0)
        ol = {"status": "healthy" if r.status_code == 200 else "unhealthy"}
    except Exception:
        ol = {"status": "unreachable"}

    services = [
        ServiceHealth(service="postgres", status=pg["status"], details=pg),
        ServiceHealth(service="age", status=age["status"], details=age),
        ServiceHealth(service="qdrant", status=qd["status"], details=qd),
        ServiceHealth(service="ollama", status=ol["status"], details=ol),
    ]
    overall = "healthy" if all(s.status == "healthy" for s in services) else "degraded"
    return FullHealthResponse(status=overall, services=services)
