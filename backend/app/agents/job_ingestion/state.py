"""
PATHS Backend - Job Ingestion Graph State
"""
from typing import TypedDict, Annotated
import operator
from uuid import UUID

class JobIngestionState(TypedDict):
    run_id: UUID | None
    source_type: str
    source_name: str
    target_urls: list[str]
    max_pages: int
    
    raw_items: Annotated[list[dict], operator.add]
    normalized_items: Annotated[list[dict], operator.add]
    
    persisted_job_ids: Annotated[list[UUID], operator.add]
    duplicate_job_ids: Annotated[list[UUID], operator.add]
    errors: Annotated[list[dict], operator.add]
    
    stats: dict
