"""
PATHS Backend - Job Ingestion Service
"""
from uuid import UUID
from datetime import datetime, timezone
import logging

from app.core.database import SessionLocal
from app.db.repositories.job_ingestion import JobIngestionRepository

logger = logging.getLogger(__name__)

class JobIngestionService:
    def __init__(self, db=None):
        self._db = db
        self._own_db = db is None

    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def _close(self):
        if self._own_db and self._db:
            self._db.close()
            self._db = None

    async def identify_duplicates(self, normalized_items: list[dict]) -> list[str]:
        hashes = [item["canonical_hash"] for item in normalized_items if "canonical_hash" in item]
        if not hashes:
            return []
        repo = JobIngestionRepository(self.db)
        existing_jobs = repo.get_jobs_by_hashes(hashes)
        duplicate_hashes = [j.canonical_hash for j in existing_jobs]
        self._close()
        return duplicate_hashes

    async def persist_jobs(self, run_id: UUID, jobs_to_persist: list[dict]) -> tuple[list[UUID], list[dict]]:
        repo = JobIngestionRepository(self.db)
        persisted_ids = []
        errors = []
        for job_data in jobs_to_persist:
            try:
                # Remove extra metadata injected by LangGraph if any, only keep valid kwargs
                # or mapped perfectly.
                job = repo.create_job(
                    source_type=job_data.get("source_type"),
                    source_name=job_data.get("source_name"),
                    source_job_id=job_data.get("source_job_id"),
                    source_url=job_data.get("source_url"),
                    canonical_hash=job_data.get("canonical_hash"),
                    company_name=job_data.get("company_name"),
                    title=job_data.get("title", "Missing Title"),
                    description_text=job_data.get("description_text"),
                    description_html=job_data.get("description_html"),
                    seniority_level=job_data.get("seniority_level"),
                    experience_level=job_data.get("experience_level"),
                    requirements=job_data.get("requirements"),
                    raw_payload_jsonb=job_data.get("raw_payload", {})
                )
                persisted_ids.append(job.id)
            except Exception as e:
                logger.error(f"Failed to persist job {job_data.get('title')}: {str(e)}")
                errors.append({
                    "source_run_id": run_id,
                    "source_type": job_data.get("source_type"),
                    "source_name": job_data.get("source_name"),
                    "source_url": job_data.get("source_url"),
                    "stage": "persist",
                    "error_type": "DatabaseError",
                    "error_message": str(e),
                    "details_jsonb": {"canonical_hash": job_data.get("canonical_hash")}
                })
        self._close()
        return persisted_ids, errors

    async def persist_raw_items(self, run_id: UUID, raw_items: list[dict]):
        repo = JobIngestionRepository(self.db)
        db_items = []
        for raw in raw_items:
            db_items.append({
                "source_run_id": run_id,
                "source_type": raw.get("source_type", "generic"),
                "source_name": raw.get("source_name", "generic"),
                "source_url": raw.get("source_url"),
                "raw_payload_jsonb": raw
            })
        if db_items:
            repo.add_raw_items(db_items)
        self._close()

    async def finalize_run(self, state: dict):
        repo = JobIngestionRepository(self.db)
        run = repo.get_source_run(state["run_id"])
        if run:
            run.finished_at = datetime.now(timezone.utc)
            run.status = "completed" if not state.get("errors") else "partial"
            run.fetched_count = len(state.get("raw_items", []))
            run.normalized_count = len(state.get("normalized_items", []))
            run.inserted_count = len(state.get("persisted_job_ids", []))
            run.duplicate_count = len(state.get("stats", {}).get("duplicate_hashes", []))
            run.failed_count = len(state.get("errors", []))
            repo.update_source_run(run)
        self._close()

    async def save_errors(self, run_id: UUID, errors: list[dict]):
        repo = JobIngestionRepository(self.db)
        # Ensure errors belong to run_id
        for e in errors:
            e["source_run_id"] = run_id
            if "source_type" not in e: e["source_type"] = "unknown"
            if "source_name" not in e: e["source_name"] = "unknown"
            if "error_message" not in e: e["error_message"] = "Unknown Error"
        repo.add_errors(errors)
        self._close()

    async def start_ingestion_run(self, source_type: str, source_name: str, target_urls: list[str], max_pages: int, created_by: str | None = None) -> UUID:
        repo = JobIngestionRepository(self.db)
        run = repo.create_source_run(source_type, source_name, created_by)
        run_id = run.id
        self._close()
        
        # In a real deployed app with Celery, we would dispatch the task here.
        # For our architecture, since `ANTI_GRAVITY_JOB_INGESTION_AGENT_SPEC.md`
        # says "otherwise compatible worker framework already present" or "FastAPI BackgroundTasks", 
        # we will handle executing the agent graph synchronously or via BackgroundTasks in the router.
        
        return run_id

    async def execute_run(self, run_id: UUID, source_type: str, source_name: str, target_urls: list[str], max_pages: int):
        from app.agents.job_ingestion.graph import build_job_ingestion_graph
        graph = build_job_ingestion_graph()
        initial_state = {
            "run_id": run_id,
            "source_type": source_type,
            "source_name": source_name,
            "target_urls": target_urls,
            "max_pages": max_pages,
            "raw_items": [],
            "normalized_items": [],
            "persisted_job_ids": [],
            "duplicate_job_ids": [],
            "errors": [],
            "stats": {}
        }
        
        # LangGraph invoke is synchronous but we can await it if we use ainvoke
        # Actually in recent langchain versions ainvoke exists. 
        # If it throws we might want to catch it.
        try:
            await graph.ainvoke(initial_state)
        except Exception as e:
            logger.error(f"Graph execution failed: {e}")
            await self.save_errors(run_id, [{"stage": "graph_execute", "error_type": "UnhandledGraphError", "error_message": str(e)}])
        
