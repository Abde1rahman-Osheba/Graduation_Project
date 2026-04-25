"""PATHS Backend — Job scraper integration package.

Wraps the external `Job_Scraper-main` project (Playwright + DuckDuckGo +
careers-page parsers) and connects it to the unified PATHS database
integration so every scraped job becomes:

    PostgreSQL jobs.id  ==  Apache AGE Job.job_id  ==  Qdrant point id
"""
