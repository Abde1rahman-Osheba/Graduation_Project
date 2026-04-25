"""Unit tests for the in-batch / fuzzy deduplication helpers."""

from __future__ import annotations

from app.services.job_scraper.job_deduplication import (
    deduplicate_in_batch,
    normalize_for_match,
)
from app.services.job_scraper.job_normalizer import normalize_one


def _raw(url: str, title: str = "Backend Engineer", company: str = "ACME Inc"):
    return {
        "job_title": title,
        "company_name": company,
        "job_url": url,
        "job_description": "Python and FastAPI experience required.",
    }


def test_normalize_for_match_strips_punct_and_lowercases():
    assert normalize_for_match("ACME Inc.") == "acme inc"
    assert normalize_for_match("  Hello  -  World  ") == "hello world"
    assert normalize_for_match(None) == ""
    assert normalize_for_match("") == ""


def test_dedup_drops_repeated_source_url():
    a = normalize_one(_raw("https://example.com/jobs/1"))
    b = normalize_one(_raw("https://example.com/jobs/1", title="Different Title"))
    c = normalize_one(_raw("https://example.com/jobs/2"))
    kept, dropped = deduplicate_in_batch([a, b, c])
    assert len(kept) == 2
    assert len(dropped) == 1
    assert dropped[0].source_url == a.source_url


def test_dedup_keeps_distinct_source_urls():
    a = normalize_one(_raw("https://example.com/jobs/1"))
    b = normalize_one(_raw("https://example.com/jobs/2"))
    kept, dropped = deduplicate_in_batch([a, b])
    assert len(kept) == 2
    assert dropped == []


def test_dedup_handles_empty_input():
    kept, dropped = deduplicate_in_batch([])
    assert kept == []
    assert dropped == []
