"""
PATHS Backend - Job Ingestion Tests
"""
import pytest
from app.adapters.job_sources.generic_html import GenericHtmlListingAdapter

@pytest.mark.asyncio
async def test_generic_html_adapter_parse():
    adapter = GenericHtmlListingAdapter()
    
    mock_html = "<html><head><title> Software Engineer </title></head><body>We are looking for a great engineer.</body></html>"
    raw_payload = {
        "html": mock_html,
        "source_url": "http://example.local/jobs"
    }
    
    parsed = await adapter.parse(raw_payload)
    
    assert len(parsed) == 1
    job = parsed[0]
    
    assert job["title"] == "Software Engineer"
    assert "looking for a great engineer" in job["description_text"]
    assert job["source_url"] == "http://example.local/jobs"
