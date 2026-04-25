"""
PATHS Backend — System / bootstrap endpoints.

These endpoints are for initial setup & testing only.
Protect or remove them before production.
"""

from fastapi import APIRouter

from app.services.age_service import AGEService
from app.services.qdrant_service import QdrantService

router = APIRouter(prefix="/system", tags=["System"])


# ── Apache AGE ─────────────────────────────────────────────────────────

@router.post("/age/init-graph")
def age_init_graph():
    """Initialize the application graph in Apache AGE."""
    return AGEService.init_graph()


@router.get("/age/sample-query")
def age_sample_query():
    """Run a sample Cypher query to verify AGE is working."""
    return AGEService.sample_query()


# ── Qdrant ─────────────────────────────────────────────────────────────

@router.post("/qdrant/init-collections")
def qdrant_init_collections():
    """Create all configured Qdrant collections if missing."""
    svc = QdrantService()
    return svc.init_collections()


@router.get("/qdrant/collections")
def qdrant_list_collections():
    """List all existing Qdrant collections."""
    svc = QdrantService()
    return {"collections": svc.list_collections()}
