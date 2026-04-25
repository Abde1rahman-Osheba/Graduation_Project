"""
PATHS — Verify the unified `job_id` across PostgreSQL, Apache AGE, Qdrant.

Usage:
    python scripts/verify_job_import_sync.py            # last 5 imported jobs
    python scripts/verify_job_import_sync.py --limit 10
    python scripts/verify_job_import_sync.py --job-id <UUID>

Exit codes:
    0  — all checked jobs passed
    1  — at least one check failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

# Allow `python scripts/verify_job_import_sync.py` from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.db.models.job import Job  # noqa: E402
from app.db.repositories import (  # noqa: E402
    candidates_graph,  # noqa: F401  (kept for parity / discoverability)
    jobs_graph,
    jobs_vector,
)


def _check_job(session, job_id: UUID) -> dict:
    pg_row = session.get(Job, job_id)
    pg_ok = pg_row is not None

    try:
        graph = jobs_graph.verify_job_graph(session, job_id)
        graph_ok = bool(graph.get("exists"))
    except Exception as exc:  # noqa: BLE001
        graph = {"error": str(exc)}
        graph_ok = False

    qdrant = jobs_vector.verify_one_vector_per_job(job_id)
    qdrant_ok = bool(qdrant.get("exists")) and qdrant.get("vector_count_for_job") == 1

    return {
        "job_id": str(job_id),
        "title": pg_row.title if pg_row else None,
        "source_url": pg_row.source_url if pg_row else None,
        "postgres": pg_ok,
        "graph": graph,
        "graph_ok": graph_ok,
        "qdrant": qdrant,
        "qdrant_ok": qdrant_ok,
        "vector_count": qdrant.get("vector_count_for_job", 0),
        "passed": pg_ok and graph_ok and qdrant_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--job-id", type=str, default=None)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.job_id:
            job_ids = [UUID(args.job_id)]
        else:
            rows = session.execute(
                select(Job)
                .where(Job.last_imported_at.isnot(None))
                .order_by(Job.last_imported_at.desc())
                .limit(max(1, int(args.limit)))
            ).scalars().all()
            job_ids = [r.id for r in rows]

        if not job_ids:
            print("No imported jobs found.")
            return 1

        all_passed = True
        for jid in job_ids:
            res = _check_job(session, jid)
            status = "PASS" if res["passed"] else "FAIL"
            print(
                f"{status} job_id={res['job_id']} "
                f"title={(res['title'] or '')[:60]!r} "
                f"postgres={res['postgres']} graph={res['graph_ok']} "
                f"qdrant={res['qdrant_ok']} vector_count={res['vector_count']}"
            )
            if not res["passed"]:
                all_passed = False

        return 0 if all_passed else 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
