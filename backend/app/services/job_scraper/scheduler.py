"""
PATHS Backend — Hourly job-scraper scheduler.

Wraps APScheduler's `AsyncIOScheduler` so the FastAPI lifespan can
start/stop a single hourly job per process. Multi-worker safety is
enforced inside `JobImportService` via a PostgreSQL advisory lock.

If APScheduler isn't installed (it's an optional dependency for the
scraper integration) the scheduler degrades to a no-op so backend
startup still succeeds.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.services.job_scraper.job_import_service import JobImportService

logger = logging.getLogger(__name__)
settings = get_settings()


_JOB_ID = "paths_hourly_job_scraper"


class JobScraperScheduler:
    """Singleton wrapper around APScheduler used by `app.main` lifespan."""

    def __init__(self) -> None:
        self._scheduler: Any | None = None
        self._service = JobImportService()
        self._started = False

    @property
    def is_active(self) -> bool:
        return bool(self._scheduler and self._started)

    @property
    def next_run_at(self) -> datetime | None:
        if not self.is_active:
            return None
        try:
            job = self._scheduler.get_job(_JOB_ID)  # type: ignore[union-attr]
            return job.next_run_time if job else None
        except Exception:  # noqa: BLE001
            return None

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        if not settings.job_scraper_enabled:
            logger.info("[JobScraperScheduler] disabled via JOB_SCRAPER_ENABLED=false")
            return
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[JobScraperScheduler] APScheduler not installed (%s) — "
                "scheduler disabled. Use the admin run-once endpoint to "
                "trigger imports manually.",
                exc,
            )
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._run_safely,
            trigger=IntervalTrigger(minutes=settings.job_scraper_interval_minutes),
            id=_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        self._started = True
        logger.info(
            "[JobScraperScheduler] started — every %d minutes, batch=%d, source=%s",
            settings.job_scraper_interval_minutes,
            settings.job_scraper_batch_size,
            settings.job_scraper_source,
        )

        if settings.job_scraper_run_on_startup:
            asyncio.create_task(self._run_safely(initial=True))

    async def shutdown(self) -> None:
        if self._scheduler is None or not self._started:
            return
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            logger.exception("[JobScraperScheduler] shutdown error (non-fatal)")
        finally:
            self._scheduler = None
            self._started = False

    # ── Run wrapper ────────────────────────────────────────────────────

    async def _run_safely(self, *, initial: bool = False) -> None:
        """Wrap `JobImportService.run_import` so exceptions never bubble up."""
        try:
            await self._service.run_import(
                limit=settings.job_scraper_batch_size,
                source=settings.job_scraper_source,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "[JobScraperScheduler] %srun crashed (will retry next interval)",
                "initial " if initial else "",
            )


# Module-level singleton
scheduler = JobScraperScheduler()


__all__ = ["scheduler", "JobScraperScheduler"]
