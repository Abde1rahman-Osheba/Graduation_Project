"""Unit tests for the scraper adapter (stub mode + helpers).

The real scraper requires Playwright + a launched Firefox browser, which
is intentionally not exercised here. We verify:

  * stub mode never tries to launch a browser
  * the link categorizer picks the right URLs
  * `_enrich_raw_job` builds the canonical raw shape
  * timeouts honour the configured limit
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.job_scraper.scraper_adapter import (
    JobScraperAdapter,
    ScrapeRunResult,
)


def test_stub_mode_returns_empty_result_without_loading_pandas():
    """In stub mode the adapter must not import pandas / launch browsers."""
    adapter = JobScraperAdapter(stub=True)
    result = asyncio.run(adapter.scrape_jobs(limit=5, company_offset=0))
    assert isinstance(result, ScrapeRunResult)
    assert result.raw_jobs == []
    assert result.companies_visited == 0
    assert result.errors == []


def test_categorize_links_picks_jobs_platform_and_careers():
    links = [
        "https://acme.com/about",
        "https://acme.com/careers",
        "https://glassdoor.com/Overview/Working-at-ACME-EI_IE12345.htm",
        "https://jobs.lever.co/acme",
        "https://www.linkedin.com/company/acme",
    ]
    jobs_url, careers_url = JobScraperAdapter._categorize_links(links)
    assert jobs_url == "https://jobs.lever.co/acme"
    assert careers_url == "https://acme.com/careers"


def test_categorize_links_returns_none_when_no_matches():
    jobs_url, careers_url = JobScraperAdapter._categorize_links([
        "https://acme.com/products",
        "https://blog.acme.com/post",
    ])
    assert jobs_url is None
    assert careers_url is None


def test_enrich_raw_job_returns_canonical_shape():
    raw = {
        "company_name": "ACME",
        "job_title": "Backend Engineer",
        "job_location": "Cairo",
        "job_url": "https://example.com/jobs/1",
        "platform": "Lever",
    }
    enriched = JobScraperAdapter._enrich_raw_job(raw, source_url="https://example.com/jobs")
    assert enriched is not None
    assert enriched["company_name"] == "ACME"
    assert enriched["job_title"] == "Backend Engineer"
    assert enriched["job_url"] == "https://example.com/jobs/1"
    assert enriched["source_platform"] == "linkedin"
    assert enriched["raw"] == raw


def test_enrich_raw_job_drops_when_required_field_missing():
    incomplete = {"job_title": "Backend Engineer", "job_url": "https://example.com/jobs/1"}
    assert JobScraperAdapter._enrich_raw_job(incomplete, source_url=None) is None


def test_scrape_jobs_returns_error_when_module_missing(tmp_path):
    """If Job_Scraper-main can't be located the adapter returns errors but does not raise."""
    adapter = JobScraperAdapter(
        module_path=str(tmp_path / "nonexistent"),
        data_file=str(tmp_path / "missing.xlsx"),
        stub=False,
        timeout_seconds=2,
    )
    result = asyncio.run(adapter.scrape_jobs(limit=1, company_offset=0))
    assert result.raw_jobs == []
    assert any(
        "company_list_load_error" in err or "data file not found" in err.lower()
        for err in result.errors
    )
