"""
PATHS Backend — Application configuration.

All settings are loaded from environment variables via pydantic-settings.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # tolerate forward-compat env vars (e.g. QDRANT_COLLECTION_CANDIDATES)
    )

    # ── Application ─────────────────────────────────────
    app_name: str = "PATHS Backend"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    # ── PostgreSQL ──────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "paths_db"
    postgres_user: str = "paths_user"
    postgres_password: str = "change_me"
    database_url: str = "postgresql+psycopg://paths_user:change_me@localhost:5432/paths_db"

    # ── Apache AGE ──────────────────────────────────────
    age_graph_name: str = "paths_graph"
    age_schema: str = "ag_catalog"

    # ── Qdrant ──────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    # Legacy chunked CV collection (kept for backward compatibility)
    qdrant_collection_cv: str = "candidate_cv_chunks"
    qdrant_collection_vector_size: int = 768  # nomic-embed-text dimension

    # ── Unified candidate / job vector collections (one-vector-per-entity rule)
    # These are the spec-compliant collections used by the new sync layer.
    qdrant_candidate_collection: str = "paths_candidates"
    qdrant_job_collection: str = "paths_jobs"

    # ── Ollama ──────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"

    # ── Embedding (provider-agnostic aliases used by sync layer) ───────
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dimension: int = 768
    embedding_version: str = "v1"

    # ── Authentication / JWT ────────────────────────────
    secret_key: str = "CHANGE-ME-TO-A-RANDOM-SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ── Ingestion ───────────────────────────────────────
    upload_dir: str = "./uploads"
    chunk_size: int = 900
    chunk_overlap: int = 120

    # ── Job Ingestion ───────────────────────────────────
    job_ingestion_enabled: bool = True
    enable_glassdoor_source: bool = False
    job_ingestion_max_pages: int = 20
    qdrant_collection_jobs: str = "job_description_chunks"

    # ── OpenRouter / Llama scoring agent ───────────────────────────────
    # Used by `app/services/scoring/*` for the candidate-job scoring service.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "meta-llama/llama-3.2-3b-instruct:free"
    openrouter_referer: str = "https://paths.local"
    openrouter_app_title: str = "PATHS Scoring Agent"
    # Decision Support System (DSS) — spec: Llama 3.2 8B
    openrouter_dss_model: str = "meta-llama/llama-3.2-8b-instruct"
    openrouter_development_model: str = "meta-llama/llama-3.2-8b-instruct"
    openrouter_outreach_model: str = "meta-llama/llama-3.2-8b-instruct"
    decision_support_enabled: bool = True
    dss_openrouter_timeout_seconds: float = 120.0
    dss_max_json_retries: int = 1

    # ── Candidate-Job scoring service ──────────────────────────────────
    scoring_service_enabled: bool = True
    scoring_agent_weight: float = 0.65
    scoring_vector_weight: float = 0.35
    scoring_min_relevance_threshold: float = 0.45
    scoring_max_jobs_per_candidate: int = 20
    scoring_model_temperature: float = 0.1
    scoring_model_max_tokens: int = 1200
    scoring_request_timeout_seconds: float = 60.0
    scoring_prompt_version: str = "v1"
    # If true, the scoring service falls back to a deterministic local
    # heuristic when no OpenRouter API key is configured (handy for
    # local dev / CI). Set to false in production.
    scoring_allow_offline_fallback: bool = True

    # ── Organization-side candidate search & outreach ──────────────────
    org_matching_enabled: bool = True
    org_matching_default_top_k: int = 3
    org_matching_max_top_k: int = 20
    org_matching_max_candidates_per_run: int = 200
    org_matching_require_human_approval: bool = True
    org_scoring_agent_weight: float = 0.65
    org_scoring_vector_weight: float = 0.35
    org_scoring_min_relevance_threshold: float = 0.45

    # LLM provider abstraction (OpenRouter | ollama)
    llm_provider: str = "openrouter"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1500
    llm_streaming_enabled: bool = True
    llm_allow_fallback_to_ollama: bool = False
    ollama_model: str = "llama3.1:8b"

    # CSV / CV download safety
    org_csv_max_rows: int = 500
    org_cv_download_timeout_seconds: int = 30
    org_cv_max_file_size_mb: int = 10
    org_cv_allowed_content_types: str = (
        "application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/msword,"
        "text/plain"
    )
    # SSRF protection — block these CIDR ranges in CV download
    org_cv_block_private_networks: bool = True

    # Outreach
    outreach_enabled: bool = True
    outreach_require_approval: bool = True
    outreach_from_email: str = ""
    outreach_from_name: str = "PATHS Recruitment"
    outreach_reply_deadline_days: int = 3
    outreach_default_booking_link: str = ""
    outreach_provider: str = "smtp"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # Optional MCP support
    mcp_enabled: bool = False
    mcp_google_calendar_enabled: bool = False
    mcp_gmail_enabled: bool = False

    # ── Interview intelligence module ───────────────────────────────────
    interview_intelligence_enabled: bool = True
    # Google Calendar + Meet (optional; service account JSON)
    google_application_credentials: str = ""
    google_calendar_service_account_file: str = ""
    google_calendar_id: str = "primary"
    google_workspace_impersonate_user: str = ""

    # ── Job Scraper (hourly LinkedIn / careers-page import) ────────────
    # Wraps the external `Job_Scraper-main` module. Hourly scheduler
    # imports at most JOB_SCRAPER_BATCH_SIZE jobs per run.
    job_scraper_enabled: bool = False  # opt-in; Playwright must be installed
    job_scraper_interval_minutes: int = 60
    job_scraper_batch_size: int = 5
    job_scraper_run_on_startup: bool = False
    job_scraper_source: str = "linkedin"
    job_scraper_timeout_seconds: int = 120
    job_scraper_max_pages_per_run: int = 1
    job_scraper_log_level: str = "INFO"
    # Filesystem locations
    job_scraper_module_path: str = "../Job_Scraper-main"
    job_scraper_data_file: str = "../Job_Scraper-main/data/Data.xlsx"
    # Per-run company budget — how many companies the adapter is allowed
    # to visit (browser pages are expensive). Resets to 0 when the list ends.
    job_scraper_companies_per_run: int = 8
    # Headless browser flag, kept controlled and slow by default
    job_scraper_headless: bool = True
    # Optional: stub the scraper (return [] always) — handy in tests/CI.
    job_scraper_stub: bool = False
    # Distributed lock name for the hourly scheduler
    job_scraper_lock_name: str = "paths_job_scraper_hourly_import"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
