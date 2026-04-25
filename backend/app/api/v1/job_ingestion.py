"""
PATHS Backend - Job Ingestion API Endpoints.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Any

from app.core.database import get_db
from sqlalchemy.orm import Session

from app.schemas.job_ingestion import (
    JobIngestionRunRequest,
    JobIngestionRunResponse,
    JobIngestionErrorResponse,
)
from app.services.job_ingestion_service import JobIngestionService
from app.db.repositories.job_ingestion import JobIngestionRepository

router = APIRouter(prefix="/internal/job-ingestion", tags=["Job Ingestion"])

@router.post("/run", response_model=dict)
async def trigger_job_ingestion(
    request: JobIngestionRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Any:
    """
    Trigger a job ingestion run in the background.
    """
    service = JobIngestionService(db=None)
    
    source_type = request.source_types[0] if request.source_types else "generic_html"
    source_name = "configured_source"
    
    if source_type == "telegram_channel":
        target_urls = request.target_urls or ["https://t.me/s/it_jobs_linkedin"]
    else:
        target_urls = request.target_urls or ["https://example.com/"] 
    max_pages = request.max_pages or 5
    
    # We await the setup since our service uses async def for DB operations
    run_id = await service.start_ingestion_run(
        source_type=source_type,
        source_name=source_name,
        target_urls=target_urls,
        max_pages=max_pages,
        created_by="api_user"
    )
    
    background_tasks.add_task(
        service.execute_run,
        run_id=run_id,
        source_type=source_type,
        source_name=source_name,
        target_urls=target_urls,
        max_pages=max_pages
    )
    
    return {"run_id": run_id, "status": "accepted"}

@router.get("/runs", response_model=list[JobIngestionRunResponse])
async def list_runs(db: Session = Depends(get_db)) -> Any:
    repo = JobIngestionRepository(db)
    runs = repo.get_all_runs()
    return runs

@router.get("/runs/{run_id}", response_model=JobIngestionRunResponse)
async def get_run(run_id: UUID, db: Session = Depends(get_db)) -> Any:
    repo = JobIngestionRepository(db)
    run = repo.get_source_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

@router.get("/errors", response_model=list[JobIngestionErrorResponse])
async def get_errors(run_id: UUID | None = None, db: Session = Depends(get_db)) -> Any:
    repo = JobIngestionRepository(db)
    if run_id:
        return repo.get_errors_by_run(run_id)
    return repo.get_all_errors()

@router.post("/reproject/{job_id}", response_model=dict)
async def reproject_job(job_id: UUID, db: Session = Depends(get_db)) -> Any:
    return {"status": "skipped", "message": "Projection not fully implemented"}
