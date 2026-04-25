"""
PATHS Backend - Job Ingestion Repository
"""
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.job_ingestion import JobSourceRun, JobRawItem, IngestionError
from app.db.models.job import Job

class JobIngestionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_source_run(self, source_type: str, source_name: str, created_by: str | None = None) -> JobSourceRun:
        run = JobSourceRun(source_type=source_type, source_name=source_name, created_by=created_by)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run
        
    def get_source_run(self, run_id: UUID) -> JobSourceRun | None:
        return self.db.get(JobSourceRun, run_id)

    def get_all_runs(self) -> Sequence[JobSourceRun]:
        stmt = select(JobSourceRun).order_by(JobSourceRun.started_at.desc())
        return self.db.scalars(stmt).all()

    def update_source_run(self, run: JobSourceRun):
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

    def get_job_by_hash(self, canonical_hash: str) -> Job | None:
        stmt = select(Job).where(Job.canonical_hash == canonical_hash)
        return self.db.scalars(stmt).first()

    def get_jobs_by_hashes(self, hashes: list[str]) -> Sequence[Job]:
        stmt = select(Job).where(Job.canonical_hash.in_(hashes))
        return self.db.scalars(stmt).all()

    def create_job(self, **kwargs) -> Job:
        job = Job(**kwargs)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def add_raw_items(self, items: list[dict]):
        db_items = [JobRawItem(**item) for item in items]
        self.db.add_all(db_items)
        self.db.commit()

    def add_errors(self, errors: list[dict]):
        db_errors = [IngestionError(**e) for e in errors]
        self.db.add_all(db_errors)
        self.db.commit()
        
    def get_errors_by_run(self, run_id: UUID) -> Sequence[IngestionError]:
        stmt = select(IngestionError).where(IngestionError.source_run_id == run_id)
        return self.db.scalars(stmt).all()

    def get_all_errors(self) -> Sequence[IngestionError]:
        stmt = select(IngestionError).order_by(IngestionError.created_at.desc())
        return self.db.scalars(stmt).all()
