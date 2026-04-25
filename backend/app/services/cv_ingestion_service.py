import logging
import uuid
import json
from io import BytesIO

from app.core.database import SessionLocal
from app.db.models.ingestion import IngestionJob
from app.agents.cv_ingestion.graph import ingestion_app
from app.agents.cv_ingestion.state import CVIngestionState

logger = logging.getLogger(__name__)

async def process_cv_job(job_id: str, candidate_id: str, file_path: str):
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, uuid.UUID(job_id))
        if not job:
            return
            
        initial_state: CVIngestionState = {
            "job_id": job_id,
            "candidate_id": candidate_id,
            "document_id": None,
            "file_path": file_path,
            "raw_text": None,
            "structured_candidate": None,
            "normalized_candidate": None,
            "chunks": None,
            "embeddings": None,
            "errors": [],
            "status": "running",
            "stage": "started"
        }
        
        # Update job
        job.status = "running"
        db.commit()
        
        # Run graph
        final_state = ingestion_app.invoke(initial_state)
        
        # Update job completion
        job = db.get(IngestionJob, uuid.UUID(job_id)) # refresh
        job.status = final_state.get("status", "failed")
        job.stage = final_state.get("stage", "done")
        
        if final_state.get("errors"):
            job.error_message = "\n".join(final_state["errors"])
        
        # if newly created
        if final_state.get("candidate_id") and job.candidate_id is None:
            job.candidate_id = uuid.UUID(final_state["candidate_id"])
        if final_state.get("document_id"):
            job.document_id = uuid.UUID(final_state["document_id"])
            
        db.commit()
    except Exception as e:
        logger.exception("Job processing failed catastrophically.")
        job = db.get(IngestionJob, uuid.UUID(job_id))
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
    finally:
        db.close()
