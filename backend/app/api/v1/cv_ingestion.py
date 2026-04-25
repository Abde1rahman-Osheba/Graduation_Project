import os
import uuid
import shutil
from fastapi import APIRouter, Depends, File, UploadFile, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.db.models.ingestion import IngestionJob
from app.services.cv_ingestion_service import process_cv_job
from app.core.config import get_settings

router = APIRouter(prefix="/cv-ingestion", tags=["CV Ingestion"])
settings = get_settings()

@router.post("/upload")
async def upload_cv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    candidate_id: str | None = None,
    db: Session = Depends(get_db)
):
    upload_dir = os.getenv("UPLOAD_DIR", "./uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    cand_uuid = uuid.UUID(candidate_id) if candidate_id else None
    
    job = IngestionJob(
        candidate_id=cand_uuid,
        status="pending",
        stage="uploaded"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    cand_id_str = str(cand_uuid) if cand_uuid else None
    
    background_tasks.add_task(process_cv_job, str(job.id), cand_id_str, file_path)
    
    return {
        "job_id": str(job.id),
        "candidate_id": str(job.candidate_id) if job.candidate_id else None,
        "status": "pending"
    }

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(IngestionJob, uuid.UUID(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return {
        "job_id": str(job.id),
        "candidate_id": str(job.candidate_id) if job.candidate_id else None,
        "document_id": str(job.document_id) if job.document_id else None,
        "stage": job.stage,
        "status": job.status,
        "error_message": job.error_message
    }
