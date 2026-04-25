"""
PATHS Backend — Job Ingestion Pydantic schemas.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class NormalizedJob(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_type: str
    source_name: str
    source_job_id: str | None = None
    source_url: str
    company_name: str
    title: str
    description_text: str
    role_family: str = "other"
    employment_type: str | None = None
    seniority_level: str | None = None
    experience_level: str | None = None
    requirements: str | None = None
    location_text: str | None = None
    location_mode: str | None = None
    country_code: str | None = None
    city: str | None = None
    department: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    posted_at: datetime | None = None
    skills: list[str] = []
    raw_payload: dict


class JobIngestionRunRequest(BaseModel):
    source_types: list[str] | None = Field(default=None, description="Specific sources to run. If none, run all enabled sources.")
    max_pages: int | None = Field(default=None, description="Override the configured max pages per source.")
    target_urls: list[str] | None = Field(default=None, description="Provide specific URLs to target directly for scraping.")


class JobIngestionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_type: str
    source_name: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    fetched_count: int
    normalized_count: int
    inserted_count: int
    updated_count: int
    duplicate_count: int
    failed_count: int
    created_by: str | None = None


class JobIngestionErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_run_id: UUID | None = None
    source_type: str
    source_name: str
    source_url: str | None = None
    stage: str
    error_type: str
    error_message: str
    details_jsonb: dict | None = None
    created_at: datetime

class JobReprojectRequest(BaseModel):
    job_id: UUID

