"""
PATHS Backend — Adapter around the existing `Job_Scraper-main` project.

Responsibilities:

  * Locate `Job_Scraper-main` on disk (defaults to a sibling directory of
    the backend, configurable via JOB_SCRAPER_MODULE_PATH).
  * Lazily import `BrowserManager` and `JobScraper` from its `src/` folder
    so that backend startup never fails when Playwright isn't installed.
  * Read the company list from `data/Data.xlsx` (configurable).
  * Walk through companies starting from a persisted offset, scrape jobs
    via the existing per-platform scrapers, and stop as soon as the
    requested limit is reached.
  * Apply a hard timeout to the whole run.
  * Always return a list of raw scraped-job dicts in the format the rest
    of the pipeline expects:

        {
            "company_name": str,
            "job_title": str,
            "job_location": str | None,
            "job_url": str,
            "posting_date": str | None,
            "job_description": str | None,
            "platform": str,
            "source_platform": "linkedin",
            "raw": {...},
        }

The adapter never raises on scraper / Playwright errors. It logs them
and returns whatever it managed to collect.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Public result objects ────────────────────────────────────────────────


@dataclass
class ScrapeRunResult:
    raw_jobs: list[dict[str, Any]] = field(default_factory=list)
    companies_visited: int = 0
    new_offset: int = 0
    errors: list[str] = field(default_factory=list)


# ── Adapter ──────────────────────────────────────────────────────────────


class JobScraperAdapter:
    """Async adapter around the `Job_Scraper-main` Playwright scraper."""

    def __init__(
        self,
        *,
        module_path: str | None = None,
        data_file: str | None = None,
        headless: bool | None = None,
        timeout_seconds: int | None = None,
        stub: bool | None = None,
    ) -> None:
        self.module_path = Path(module_path or settings.job_scraper_module_path).resolve()
        self.data_file = Path(data_file or settings.job_scraper_data_file).resolve()
        self.headless = settings.job_scraper_headless if headless is None else headless
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.job_scraper_timeout_seconds
        )
        self.stub = settings.job_scraper_stub if stub is None else stub

    # ── Loading ────────────────────────────────────────────────────────

    def _add_module_to_path(self) -> None:
        src_path = self.module_path / "src"
        for p in (str(self.module_path), str(src_path)):
            if p not in sys.path:
                sys.path.insert(0, p)

    def _load_browser_manager(self):
        """Import `BrowserManager` from Job_Scraper-main lazily."""
        self._add_module_to_path()
        try:
            module = importlib.import_module("scrapper")
            return module.BrowserManager
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Could not import scrapper.BrowserManager from {self.module_path}: {exc}"
            ) from exc

    def _load_job_scraper(self):
        self._add_module_to_path()
        try:
            module = importlib.import_module("job_scraper")
            return module.JobScraper
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Could not import job_scraper.JobScraper from {self.module_path}: {exc}"
            ) from exc

    def _load_companies(
        self, offset: int, limit: int,
    ) -> tuple[list[dict[str, str]], int]:
        """Read the next `limit` companies from the Excel sheet.

        Returns (companies, total_company_count). Companies wrap around to
        offset 0 once the end of the list is reached.
        """
        try:
            import pandas as pd  # local import: optional dependency
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "pandas is required to read the scraper company list. "
                "Install pandas + openpyxl, or set JOB_SCRAPER_STUB=true."
            ) from exc

        if not self.data_file.exists():
            raise RuntimeError(
                f"Job_Scraper-main data file not found at {self.data_file}. "
                f"Set JOB_SCRAPER_DATA_FILE or JOB_SCRAPER_STUB=true."
            )

        df = pd.read_excel(self.data_file)
        total = len(df)
        if total == 0:
            return [], 0

        # Safe wrap-around: e.g. offset=170, limit=8, total=173 → [170, 171, 172, 0, 1, 2, 3, 4]
        offset = offset % total
        rows: list[dict[str, str]] = []
        for i in range(limit):
            idx = (offset + i) % total
            row = df.iloc[idx]
            name = str(row.get("Company Name", "")).strip()
            description = str(row.get("Company Description", "")).strip()
            if not name:
                continue
            rows.append({"name": name, "description": description})
        return rows, total

    # ── Public scraping API ────────────────────────────────────────────

    async def scrape_jobs(
        self,
        *,
        limit: int = 5,
        company_offset: int = 0,
        companies_per_run: int | None = None,
    ) -> ScrapeRunResult:
        """Scrape up to `limit` raw jobs from the next batch of companies.

        Args:
            limit: max number of jobs returned this run (the spec cap of 5
                is enforced by the calling import service).
            company_offset: where to start in the company list. Use the
                value persisted in `job_scraper_state.company_offset`.
            companies_per_run: how many companies the adapter is allowed to
                visit (browser launches are expensive; default from config).

        Returns:
            ScrapeRunResult with raw jobs + the next offset to persist.
        """
        budget = companies_per_run or settings.job_scraper_companies_per_run
        result = ScrapeRunResult(new_offset=company_offset)

        if self.stub or settings.job_scraper_stub:
            logger.info("[JobScraperAdapter] stub mode — returning [] (no browser launched)")
            return result

        # Load companies first; if this fails, abort cleanly.
        try:
            companies, total = self._load_companies(company_offset, budget)
        except Exception as exc:
            logger.exception("[JobScraperAdapter] failed to load companies")
            result.errors.append(f"company_list_load_error: {exc}")
            return result
        if not companies or total == 0:
            return result

        try:
            BrowserManager = self._load_browser_manager()
            JobScraper = self._load_job_scraper()
        except Exception as exc:
            logger.error("[JobScraperAdapter] %s", exc)
            result.errors.append(str(exc))
            return result

        try:
            result = await asyncio.wait_for(
                self._run_browser_scrape(
                    BrowserManager=BrowserManager,
                    JobScraper=JobScraper,
                    companies=companies,
                    limit=limit,
                    base_offset=company_offset,
                    total=total,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[JobScraperAdapter] scrape timed out after %ss",
                self.timeout_seconds,
            )
            result.errors.append("timeout")
        except Exception as exc:
            logger.exception("[JobScraperAdapter] unexpected scraper failure")
            result.errors.append(f"adapter_error: {exc}")
        return result

    # ── Browser scrape (runs inside the timeout) ───────────────────────

    async def _run_browser_scrape(
        self,
        *,
        BrowserManager: Any,
        JobScraper: Any,
        companies: list[dict[str, str]],
        limit: int,
        base_offset: int,
        total: int,
    ) -> ScrapeRunResult:
        out = ScrapeRunResult(new_offset=base_offset)
        bm = BrowserManager(max_concurrent_tabs=2, headless=self.headless)
        await bm.initialize()
        scraper = JobScraper(bm, max_concurrent_scrapes=1)

        try:
            for idx, company in enumerate(companies):
                if len(out.raw_jobs) >= limit:
                    break
                out.companies_visited += 1
                name = company["name"]
                logger.info("[JobScraperAdapter] visiting company: %s", name)

                # 1. Discover jobs/careers URLs through DuckDuckGo
                discovery_queries = [
                    f"{name} jobs",
                    f"{name} careers",
                    f"{name} lever jobs",
                    f"{name} greenhouse careers",
                    f"{name} workday jobs",
                ]
                try:
                    links = await bm.search_multiple(discovery_queries, name)
                except Exception as exc:  # noqa: BLE001
                    out.errors.append(f"search:{name}:{exc}")
                    continue

                jobs_url, careers_url = self._categorize_links(links)
                if not jobs_url and not careers_url:
                    continue

                # 2. Scrape jobs from the discovered URL(s)
                try:
                    discovered: list[dict[str, Any]] = []
                    if jobs_url:
                        discovered.extend(
                            await scraper.scrape_jobs_from_url(name, jobs_url, "jobs")
                        )
                    if len(discovered) < 1 and careers_url:
                        discovered.extend(
                            await scraper.scrape_jobs_from_url(
                                name, careers_url, "careers",
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    out.errors.append(f"scrape:{name}:{exc}")
                    continue

                # 3. Convert + accept up to remaining limit
                for raw in discovered:
                    if len(out.raw_jobs) >= limit:
                        break
                    enriched = self._enrich_raw_job(raw, jobs_url or careers_url)
                    if enriched:
                        out.raw_jobs.append(enriched)
        finally:
            try:
                await scraper.cleanup_scraper_tabs()
            except Exception:  # noqa: BLE001
                pass
            try:
                await bm.close()
            except Exception:  # noqa: BLE001
                pass

        # Compute the next offset so the next run continues where we stopped
        out.new_offset = (base_offset + out.companies_visited) % total
        return out

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _categorize_links(links: Iterable[str]) -> tuple[str | None, str | None]:
        """Pick a likely jobs-platform URL and a careers URL from raw links."""
        jobs_url: str | None = None
        careers_url: str | None = None
        platform_hosts = (
            "lever.co",
            "greenhouse.io",
            "zohorecruit.com",
            "smartrecruiters.com",
            "workday.com",
            "bamboohr.com",
            "jobvite.com",
            "icims.com",
            "teamtailor.com",
            "personio.com",
        )
        career_keywords = (
            "careers",
            "jobs",
            "employment",
            "opportunities",
            "hiring",
            "openings",
            "join-us",
            "work-with-us",
        )
        excluded = (
            "glassdoor.com",
            "indeed.com",
            "monster.com",
            "ziprecruiter.com",
        )
        for link in links:
            ll = link.lower()
            if not jobs_url and any(host in ll for host in platform_hosts):
                jobs_url = link
                continue
            if (
                not careers_url
                and any(k in ll for k in career_keywords)
                and not any(host in ll for host in excluded)
                and not any(host in ll for host in platform_hosts)
            ):
                careers_url = link
        return jobs_url, careers_url

    @staticmethod
    def _enrich_raw_job(raw: dict[str, Any], source_url: str | None) -> dict[str, Any] | None:
        """Wrap the scraper's raw dict into the canonical raw shape."""
        title = (raw.get("job_title") or raw.get("title") or "").strip()
        job_url = (raw.get("job_url") or raw.get("url") or "").strip()
        company = (raw.get("company_name") or raw.get("company") or "").strip()
        if not title or not job_url or not company:
            return None
        return {
            "company_name": company,
            "job_title": title,
            "job_location": (raw.get("job_location") or raw.get("location") or "").strip()
            or None,
            "job_url": job_url,
            "posting_date": (raw.get("posting_date") or raw.get("posted") or "").strip()
            or None,
            "job_description": (raw.get("job_description") or raw.get("description") or "").strip()
            or None,
            "platform": raw.get("platform") or "Unknown",
            "source_platform": settings.job_scraper_source,
            "source_url": source_url,
            "raw": raw,
        }
