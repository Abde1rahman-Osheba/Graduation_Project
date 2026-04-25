"""
PATHS Backend — Database health service.

Exposes a single `check_all` function that returns the spec-compliant
shape used by `GET /health/databases`:

    {
      "postgres":   { "status": "connected", "details": "..." },
      "apache_age": { "status": "connected", "graph": "...", "details": "..." },
      "qdrant":     { "status": "connected", "candidate_collection": "...",
                      "job_collection": "...", "details": "..." }
    }

Connection failures never expose passwords or DSNs.
"""

from __future__ import annotations

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine
from app.db.repositories import candidates_vector, jobs_vector

logger = logging.getLogger(__name__)
settings = get_settings()


def _safe_error(exc: Exception) -> str:
    """Return a redacted error message safe to expose in HTTP responses."""
    msg = str(exc)
    secrets_to_mask = [
        settings.postgres_password,
        settings.qdrant_api_key,
    ]
    for s in secrets_to_mask:
        if s:
            msg = msg.replace(s, "***")
    return msg[:500]


def check_postgres() -> dict[str, Any]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_name = conn.execute(text("SELECT current_database()")).scalar()
        return {
            "status": "connected",
            "database": db_name,
            "details": "SELECT 1 succeeded",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "details": _safe_error(exc)}


def check_apache_age() -> dict[str, Any]:
    try:
        with engine.connect() as conn:
            ext = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname='age'")
            ).scalar()
            if not ext:
                return {
                    "status": "error",
                    "graph": settings.age_graph_name,
                    "details": "AGE extension is not installed",
                }
            conn.execute(text("LOAD 'age';"))
            conn.execute(
                text(f"SET search_path = {settings.age_schema}, \"$user\", public;")
            )
            graph_row = conn.execute(
                text("SELECT 1 FROM ag_catalog.ag_graph WHERE name = :g"),
                {"g": settings.age_graph_name},
            ).first()
            if not graph_row:
                return {
                    "status": "degraded",
                    "graph": settings.age_graph_name,
                    "details": (
                        f"AGE installed (v{ext}) but graph "
                        f"'{settings.age_graph_name}' not yet created"
                    ),
                }
        return {
            "status": "connected",
            "graph": settings.age_graph_name,
            "details": f"AGE extension loaded (v{ext}) and graph accessible",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "graph": settings.age_graph_name,
            "details": _safe_error(exc),
        }


def check_qdrant() -> dict[str, Any]:
    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=5,
        )
        existing = {c.name for c in client.get_collections().collections}
        cand_ok = settings.qdrant_candidate_collection in existing
        job_ok = settings.qdrant_job_collection in existing
        details_parts: list[str] = []
        if cand_ok:
            details_parts.append(
                f"candidate collection '{settings.qdrant_candidate_collection}' present"
            )
        else:
            details_parts.append(
                f"candidate collection '{settings.qdrant_candidate_collection}' missing"
            )
        if job_ok:
            details_parts.append(
                f"job collection '{settings.qdrant_job_collection}' present"
            )
        else:
            details_parts.append(
                f"job collection '{settings.qdrant_job_collection}' missing"
            )
        status = "connected" if cand_ok and job_ok else "degraded"
        return {
            "status": status,
            "candidate_collection": settings.qdrant_candidate_collection,
            "job_collection": settings.qdrant_job_collection,
            "details": "; ".join(details_parts),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "candidate_collection": settings.qdrant_candidate_collection,
            "job_collection": settings.qdrant_job_collection,
            "details": _safe_error(exc),
        }


def check_all() -> dict[str, Any]:
    return {
        "postgres": check_postgres(),
        "apache_age": check_apache_age(),
        "qdrant": check_qdrant(),
    }


def ensure_qdrant_collections() -> dict[str, Any]:
    """Create the candidate and job Qdrant collections if missing."""
    try:
        cand = candidates_vector.ensure_candidate_collection()
        job = jobs_vector.ensure_job_collection()
        return {"status": "ok", "candidate": cand, "job": job}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "details": _safe_error(exc)}
