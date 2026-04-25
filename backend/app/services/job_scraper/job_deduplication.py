"""
PATHS Backend — Job deduplication helpers.

Implements the two spec checks from `02_POSTGRES_JOB_IMPORT_REQUIREMENTS.md`
and `06_UNIFIED_JOB_ID_AND_SYNC_CHECKLIST.md`:

  1. Primary: same `(source_platform, source_url)` already exists.
  2. Secondary: same `normalized_title + normalized_company + normalized_location`
     already exists (best-effort fallback when URLs change between runs).

These helpers live separately from the repository so the import service
can decide how to react (skip vs update) without round-tripping through
the database for trivially-equivalent rows in the same batch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.job import Job
from app.services.job_scraper.job_normalizer import NormalizedJob


_NORMALIZE_RE = re.compile(r"[\s\-_/.,()&'\"]+")


def normalize_for_match(value: str | None) -> str:
    """Lowercase + strip punctuation/whitespace for fuzzy matching."""
    if not value:
        return ""
    return _NORMALIZE_RE.sub(" ", value.strip().lower()).strip()


# ── In-batch dedup ───────────────────────────────────────────────────────


def deduplicate_in_batch(
    jobs: Iterable[NormalizedJob],
) -> tuple[list[NormalizedJob], list[NormalizedJob]]:
    """Drop later occurrences of the same `(source_platform, source_url)`."""
    seen: set[tuple[str, str]] = set()
    kept: list[NormalizedJob] = []
    dropped: list[NormalizedJob] = []
    for job in jobs:
        key = (job.source_platform, job.source_url)
        if key in seen:
            dropped.append(job)
            continue
        seen.add(key)
        kept.append(job)
    return kept, dropped


# ── Database lookups ─────────────────────────────────────────────────────


@dataclass
class DuplicateMatch:
    """Result describing how a normalized job matches an existing row."""

    job_id: str
    match_type: str  # "primary" or "secondary"


def find_existing_by_source(
    db: Session, normalized: NormalizedJob,
) -> Job | None:
    """Primary match: identical (source_platform, source_url)."""
    if not normalized.source_url:
        return None
    return db.execute(
        select(Job).where(
            Job.source_platform == normalized.source_platform,
            Job.source_url == normalized.source_url,
        )
    ).scalar_one_or_none()


def find_existing_by_attributes(
    db: Session, normalized: NormalizedJob,
) -> Job | None:
    """Secondary fallback: same title + company + location for the same source."""
    title_norm = normalize_for_match(normalized.title)
    company_norm = normalize_for_match(normalized.company_name)
    location_norm = normalize_for_match(normalized.location_text)
    if not title_norm or not company_norm:
        return None

    candidates = db.execute(
        select(Job).where(
            Job.title_normalized == title_norm,
            Job.company_normalized == company_norm,
            Job.source_platform == normalized.source_platform,
        )
    ).scalars().all()

    for job in candidates:
        if normalize_for_match(job.location_text) == location_norm:
            return job
    return candidates[0] if candidates else None


def find_existing(db: Session, normalized: NormalizedJob) -> Job | None:
    """Return the existing Job row that matches (primary then secondary)."""
    existing = find_existing_by_source(db, normalized)
    if existing is not None:
        return existing
    return find_existing_by_attributes(db, normalized)


__all__ = [
    "DuplicateMatch",
    "deduplicate_in_batch",
    "find_existing",
    "find_existing_by_attributes",
    "find_existing_by_source",
    "normalize_for_match",
]
