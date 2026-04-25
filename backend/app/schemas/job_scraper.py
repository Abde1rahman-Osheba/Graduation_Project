"""
PATHS Backend — Job-scraper Pydantic schemas.

Used by the admin router (`/admin/job-import/...`) and the
JobImportService.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobImportResult(BaseModel):
    """Spec-compliant result returned by `JobImportService.run_import`."""

    import_run_id: str | None = None
    source_platform: str
    requested_limit: int
    scraped_count: int = 0
    valid_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    graph_synced_count: int = 0
    vector_synced_count: int = 0
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "success"  # success | partial | failed | locked
    errors: list[str] = Field(default_factory=list)
    job_ids: list[str] = Field(default_factory=list)


class JobImportRunRequest(BaseModel):
    """Body of `POST /admin/job-import/run-once`."""

    limit: int | None = None
    source: str | None = None


class JobImportRunSummary(BaseModel):
    """Lightweight summary used by the history endpoint."""

    id: str
    source_platform: str
    started_at: datetime
    finished_at: datetime | None = None
    requested_limit: int
    scraped_count: int
    valid_count: int
    inserted_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    graph_synced_count: int
    vector_synced_count: int
    status: str
    error_message: str | None = None


class JobImportStatus(BaseModel):
    enabled: bool
    interval_minutes: int
    batch_size: int
    source: str
    last_run: JobImportRunSummary | None = None
    next_run_at: datetime | None = None
    scheduler_active: bool = False
    metadata: dict[str, Any] | None = None
