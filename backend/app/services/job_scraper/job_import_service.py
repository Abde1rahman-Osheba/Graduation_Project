"""
PATHS Backend — Hourly job import orchestration service.

Implements the full pipeline described in
`05_HOURLY_SCHEDULER_AND_IMPORT_SERVICE.md`:

  1. Acquire a PostgreSQL advisory lock so multi-worker deploys never
     run two scraper imports concurrently.
  2. Create a `job_import_runs` row.
  3. Ask the scraper adapter for raw jobs (capped at `batch_size`).
  4. Normalize + validate them, log rejections to `job_import_errors`.
  5. For each valid job, in its own transaction:
       a. Upsert company.
       b. Upsert job (PostgreSQL canonical id).
       c. Replace skills/requirements/responsibilities.
       d. Sync to Apache AGE.
       e. Sync to Qdrant (one vector per job, point id = jobs.id).
       f. Update sync status flags on `jobs`.
  6. Finalize the import run with success/partial/failed status.

Failures in graph or vector sync are logged but never delete the
PostgreSQL job — the `/admin/sync/job/{id}/retry` endpoint or the next
hourly run can recover them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.db.repositories import job_scraper_repo as repo
from app.schemas.job_scraper import JobImportResult
from app.services.job_scraper.job_deduplication import deduplicate_in_batch
from app.services.job_scraper.job_normalizer import (
    NormalizedJob,
    normalize_scraped_jobs,
)
from app.services.job_scraper.scraper_adapter import (
    JobScraperAdapter,
    ScrapeRunResult,
)
from app.services.job_sync_service import sync_job_full

logger = logging.getLogger(__name__)
settings = get_settings()


class JobImportService:
    """Coordinates scraper → normalize → PostgreSQL → AGE → Qdrant."""

    def __init__(
        self,
        *,
        adapter: JobScraperAdapter | None = None,
        session_factory=SessionLocal,
    ) -> None:
        self._adapter = adapter or JobScraperAdapter()
        self._session_factory = session_factory

    # ── Public API ─────────────────────────────────────────────────────

    async def run_import(
        self,
        *,
        limit: int | None = None,
        source: str | None = None,
        admin_override: bool = False,
    ) -> JobImportResult:
        """Run a single import cycle. Returns the summary in spec format."""
        source_platform = source or settings.job_scraper_source

        # Spec rule: hourly run is hard-capped at 5; admin override may
        # bypass the cap if explicitly requested.
        if limit is None:
            limit = settings.job_scraper_batch_size
        if not admin_override:
            limit = min(int(limit), int(settings.job_scraper_batch_size))
        limit = max(1, int(limit))

        started = datetime.now(timezone.utc)
        result = JobImportResult(
            source_platform=source_platform,
            requested_limit=limit,
            started_at=started,
        )

        # ── Acquire PostgreSQL advisory lock ───────────────────────────
        lock_session: Session = self._session_factory()
        try:
            locked = self._try_acquire_lock(
                lock_session, settings.job_scraper_lock_name,
            )
            if not locked:
                logger.info(
                    "[JobImport] another worker holds the import lock; skipping",
                )
                result.status = "locked"
                result.finished_at = datetime.now(timezone.utc)
                return result

            await self._run_locked(result, source_platform=source_platform, limit=limit)
        finally:
            self._release_lock(lock_session, settings.job_scraper_lock_name)
            try:
                lock_session.close()
            except Exception:  # noqa: BLE001
                pass

        result.finished_at = datetime.now(timezone.utc)
        logger.info(
            "[JobImport] finished status=%s scraped=%d valid=%d inserted=%d "
            "updated=%d skipped=%d failed=%d graph_synced=%d vector_synced=%d",
            result.status,
            result.scraped_count,
            result.valid_count,
            result.inserted_count,
            result.updated_count,
            result.skipped_count,
            result.failed_count,
            result.graph_synced_count,
            result.vector_synced_count,
        )
        return result

    # ── Locked section ─────────────────────────────────────────────────

    async def _run_locked(
        self,
        result: JobImportResult,
        *,
        source_platform: str,
        limit: int,
    ) -> None:
        # 1. Open the import-run row in its own session
        run_session: Session = self._session_factory()
        run_id: UUID | None = None
        try:
            run = repo.create_import_run(
                run_session,
                source_platform=source_platform,
                requested_limit=limit,
                metadata={"started_via": "scheduler"},
            )
            run_id = run.id
            run_session.commit()
            result.import_run_id = str(run.id)
        except Exception as exc:  # noqa: BLE001
            run_session.rollback()
            logger.exception("[JobImport] could not create import run")
            result.status = "failed"
            result.errors.append(f"create_import_run: {exc}")
            run_session.close()
            return

        # 2. Resolve scraping offset
        try:
            state = repo.get_state(run_session, source_platform)
            company_offset = state.company_offset
            run_session.commit()
        except Exception:
            company_offset = 0
            run_session.rollback()
        finally:
            run_session.close()

        logger.info(
            "[JobImport] started source=%s limit=%d run_id=%s offset=%d",
            source_platform, limit, result.import_run_id, company_offset,
        )

        # 3. Scrape (no DB session held during browser work)
        try:
            scrape: ScrapeRunResult = await self._adapter.scrape_jobs(
                limit=limit,
                company_offset=company_offset,
                companies_per_run=settings.job_scraper_companies_per_run,
            )
            result.scraped_count = len(scrape.raw_jobs)
            result.errors.extend(scrape.errors)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[JobImport] scraper failed")
            self._finalize_run(
                run_id,
                result,
                status="failed",
                error_message=f"scraper_error: {exc}",
            )
            result.status = "failed"
            return

        # 4. Normalize + validate + dedup
        normalized, rejected = normalize_scraped_jobs(scrape.raw_jobs)
        normalized, dropped = deduplicate_in_batch(normalized)
        result.valid_count = len(normalized)

        if rejected or dropped:
            self._log_rejections(run_id, source_platform, rejected, dropped)

        # 5. Process valid jobs (each in its own transaction)
        for normalized_job in normalized[:limit]:
            try:
                operation, job_id = self._upsert_job(normalized_job)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "[JobImport] upsert failed for %s — %s",
                    normalized_job.title, exc,
                )
                result.failed_count += 1
                self._log_error(
                    run_id,
                    normalized=normalized_job,
                    error_type="UpsertError",
                    error_message=str(exc),
                )
                continue

            if operation == "inserted":
                result.inserted_count += 1
            elif operation == "updated":
                result.updated_count += 1
            else:
                result.skipped_count += 1
            result.job_ids.append(str(job_id))

            # Sync to AGE / Qdrant via existing job_sync_service
            sync_outcome = self._sync_job_to_unified_stores(job_id)
            if sync_outcome["graph"]:
                result.graph_synced_count += 1
            if sync_outcome["vector"]:
                result.vector_synced_count += 1
            if sync_outcome["graph_error"]:
                result.errors.append(
                    f"graph:{job_id}:{sync_outcome['graph_error']}"
                )
            if sync_outcome["vector_error"]:
                result.errors.append(
                    f"vector:{job_id}:{sync_outcome['vector_error']}"
                )

        # 6. Persist the new offset for the next run
        try:
            update_session: Session = self._session_factory()
            try:
                repo.advance_state(
                    update_session,
                    source_platform=source_platform,
                    new_offset=scrape.new_offset,
                    last_imported_count=result.inserted_count + result.updated_count,
                )
                update_session.commit()
            finally:
                update_session.close()
        except Exception:  # noqa: BLE001
            logger.exception("[JobImport] could not advance scraper state")

        # 7. Finalize run row
        status = "success"
        if result.failed_count > 0 and result.inserted_count + result.updated_count == 0:
            status = "failed"
        elif result.failed_count > 0 or result.errors:
            status = "partial"
        self._finalize_run(
            run_id,
            result,
            status=status,
            error_message=None if status == "success" else "; ".join(result.errors[:5]) or None,
        )
        result.status = status

    # ── Per-job database work (own session) ────────────────────────────

    def _upsert_job(self, normalized: NormalizedJob) -> tuple[str, UUID]:
        session: Session = self._session_factory()
        try:
            company = repo.upsert_company(session, normalized.company_name)
            job, operation = repo.upsert_job(session, normalized, company)
            repo.replace_job_skills(
                session,
                job.id,
                required_skills=normalized.required_skills,
                preferred_skills=normalized.preferred_skills,
            )
            repo.replace_job_requirements(session, job.id, normalized.requirements)
            repo.replace_job_responsibilities(
                session, job.id, normalized.responsibilities,
            )
            session.commit()
            return operation, job.id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _sync_job_to_unified_stores(self, job_id: UUID) -> dict[str, Any]:
        out: dict[str, Any] = {
            "graph": False,
            "vector": False,
            "graph_error": None,
            "vector_error": None,
        }
        session: Session = self._session_factory()
        try:
            sync_result = sync_job_full(session, job_id)
            graph = sync_result.get("graph", {})
            vector = sync_result.get("vector", {})

            if graph.get("status") == "success":
                out["graph"] = True
                repo.mark_graph_sync(session, job_id, status="synced")
            else:
                out["graph_error"] = graph.get("error") or graph.get("status")
                repo.mark_graph_sync(
                    session, job_id, status="failed", error=str(out["graph_error"]),
                )

            if vector.get("status") in {"success", "unchanged"}:
                out["vector"] = True
                repo.mark_vector_sync(session, job_id, status="synced")
            else:
                out["vector_error"] = vector.get("error") or vector.get("status")
                repo.mark_vector_sync(
                    session, job_id, status="failed", error=str(out["vector_error"]),
                )
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            logger.exception("[JobImport] sync_job_full failed for %s", job_id)
            out["graph_error"] = str(exc)
            out["vector_error"] = str(exc)
        finally:
            session.close()
        return out

    # ── Logging helpers ────────────────────────────────────────────────

    def _log_rejections(
        self,
        run_id: UUID | None,
        source_platform: str,
        rejected: list,
        dropped: list,
    ) -> None:
        if not rejected and not dropped:
            return
        session: Session = self._session_factory()
        try:
            for r in rejected:
                raw = r.raw or {}
                repo.log_import_error(
                    session,
                    import_run_id=run_id,
                    source_platform=source_platform,
                    source_url=(raw.get("source_url") or raw.get("job_url") or ""),
                    job_title=(raw.get("title") or raw.get("job_title") or ""),
                    company_name=(raw.get("company_name") or raw.get("company") or ""),
                    error_type="ValidationError",
                    error_message=", ".join(r.reasons),
                    raw_payload={"raw": raw},
                )
            for d in dropped:
                repo.log_import_error(
                    session,
                    import_run_id=run_id,
                    source_platform=source_platform,
                    source_url=d.source_url,
                    job_title=d.title,
                    company_name=d.company_name,
                    error_type="DuplicateInBatch",
                    error_message="duplicate (source_platform, source_url) within batch",
                    raw_payload=None,
                )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("[JobImport] failed to log rejections")
        finally:
            session.close()

    def _log_error(
        self,
        run_id: UUID | None,
        *,
        normalized: NormalizedJob,
        error_type: str,
        error_message: str,
    ) -> None:
        session: Session = self._session_factory()
        try:
            repo.log_import_error(
                session,
                import_run_id=run_id,
                source_platform=normalized.source_platform,
                source_url=normalized.source_url,
                job_title=normalized.title,
                company_name=normalized.company_name,
                error_type=error_type,
                error_message=error_message,
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("[JobImport] failed to log per-job error")
        finally:
            session.close()

    def _finalize_run(
        self,
        run_id: UUID | None,
        result: JobImportResult,
        *,
        status: str,
        error_message: str | None,
    ) -> None:
        if run_id is None:
            return
        session: Session = self._session_factory()
        try:
            from app.db.models.job_scraper import JobImportRun

            run = session.get(JobImportRun, run_id)
            if run is None:
                return
            repo.finish_import_run(
                session,
                run,
                status=status,
                counts={
                    "scraped_count": result.scraped_count,
                    "valid_count": result.valid_count,
                    "inserted_count": result.inserted_count,
                    "updated_count": result.updated_count,
                    "skipped_count": result.skipped_count,
                    "failed_count": result.failed_count,
                    "graph_synced_count": result.graph_synced_count,
                    "vector_synced_count": result.vector_synced_count,
                },
                error_message=error_message,
                metadata={"job_ids": result.job_ids[:50]},
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("[JobImport] failed to finalize import run")
        finally:
            session.close()

    # ── Advisory lock helpers ──────────────────────────────────────────

    @staticmethod
    def _try_acquire_lock(session: Session, lock_name: str) -> bool:
        try:
            locked = session.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:n))"),
                {"n": lock_name},
            ).scalar()
            return bool(locked)
        except Exception:  # noqa: BLE001
            logger.exception("[JobImport] advisory lock acquire failed")
            return False

    @staticmethod
    def _release_lock(session: Session, lock_name: str) -> None:
        try:
            session.execute(
                text("SELECT pg_advisory_unlock(hashtext(:n))"),
                {"n": lock_name},
            )
            session.commit()
        except Exception:  # noqa: BLE001
            logger.warning("[JobImport] advisory lock release failed (non-fatal)")
