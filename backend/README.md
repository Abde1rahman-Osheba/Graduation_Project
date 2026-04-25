# PATHS Backend — CV Ingestion Agent

A production-ready AI ingestion agent for the **PATHS** hiring platform that accepts CVs, extracts and normalizes candidate information using a local LLM, and persistently stores data across three synchronized stores.

## Architecture

```
CV Upload → FastAPI → LangGraph Agent Pipeline
                         │
                         ├─ 1. Load document (PDF/DOCX/TXT)
                         ├─ 2. Extract text
                         ├─ 3. Structured extraction (Ollama + deterministic)
                         ├─ 4. Normalize entities (dedupe, clean, validate)
                         ├─ 5. Persist to PostgreSQL (canonical source of truth)
                         ├─ 6. Project to Apache AGE (graph relationships)
                         ├─ 7. Chunk document (section-aware splitting)
                         ├─ 8. Embed chunks (nomic-embed-text via Ollama)
                         ├─ 9. Upsert to Qdrant (vector search)
                         └─ 10. Finalize job
```

All stores share a **unified `candidate_id` UUID** for consistency.

### Data Stores

| Store | Purpose | Content |
|-------|---------|---------|
| **PostgreSQL** | Canonical relational data | Candidates, skills, experiences, education, certifications |
| **Apache AGE** | Graph relationships | Candidate→Skill, Candidate→Company, Candidate→Education |
| **Qdrant** | Semantic vector search | Embedded CV text chunks for RAG retrieval |

## Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Conda (Miniconda recommended)

## Quick Start

### 1. Start Infrastructure Services

```bash
cd backend
docker compose up -d postgres qdrant ollama
```

### 2. Enable Apache AGE Extension

The `apache/age:latest` Docker image comes with AGE pre-installed. Initialize the graph:

```bash
docker exec -it paths_postgres psql -U paths_user -d paths_db -c "CREATE EXTENSION IF NOT EXISTS age;"
docker exec -it paths_postgres psql -U paths_user -d paths_db -c "LOAD 'age'; SET search_path = ag_catalog, \"\$user\", public; SELECT create_graph('paths_graph');"
```

Or run the init script:
```bash
docker exec -i paths_postgres psql -U paths_user -d paths_db < scripts/init_age.sql
```

### 3. Pull Local Models (Ollama)

```bash
# Pull the LLM for structured extraction
docker exec -it paths_ollama ollama pull llama3.1:8b

# Pull the embedding model
docker exec -it paths_ollama ollama pull nomic-embed-text
```

### 4. Environment Setup

```bash
# Copy and edit environment file
cp .env.example .env
# Edit .env for local development (localhost instead of Docker service names)
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Run Migrations

```bash
alembic upgrade head
```

### 7. Start the Application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

### Upload CV
```bash
POST /api/v1/cv-ingestion/upload
# Multipart file upload, accepts PDF, DOCX, or TXT
curl -X POST http://localhost:8000/api/v1/cv-ingestion/upload \
  -F "file=@resume.pdf"
```

### Check Job Status
```bash
GET /api/v1/cv-ingestion/jobs/{job_id}
```

### Get Candidate Data
```bash
GET /api/v1/candidates/{candidate_id}
```

### Health Check
```bash
GET /health
# Returns per-service status: postgres, age, qdrant, ollama
```

## Testing & Verification

### Run Integration Test
```bash
# With the API running:
python scripts/verify_ingestion.py

# Or with pytest:
pytest app/tests/integration/test_cv_ingestion_pipeline.py -v -s
```

### Verify Data in PostgreSQL
```bash
docker exec -it paths_postgres psql -U paths_user -d paths_db -c "SELECT id, full_name, email FROM candidates;"
docker exec -it paths_postgres psql -U paths_user -d paths_db -c "SELECT * FROM candidate_skills;"
```

### Verify Apache AGE Graph
```bash
docker exec -it paths_postgres psql -U paths_user -d paths_db -c "LOAD 'age'; SET search_path = ag_catalog, \"\$user\", public; SELECT * FROM cypher('paths_graph', \$\$MATCH (n:Candidate) RETURN n\$\$) as (v agtype);"
```

### Verify Qdrant Vectors
```bash
curl http://localhost:6333/collections/candidate_cv_chunks
```

## Project Structure

```
backend/
├── app/
│   ├── main.py                          # FastAPI app + root health endpoint
│   ├── core/
│   │   ├── config.py                    # Pydantic settings from env
│   │   ├── database.py                  # SQLAlchemy engine & session
│   │   ├── logging.py                   # Structured logging
│   │   └── security.py                  # Auth utilities
│   ├── api/v1/
│   │   ├── health.py                    # Health check endpoints
│   │   ├── cv_ingestion.py              # Upload + job status endpoints
│   │   ├── candidates.py                # Candidate preview endpoint
│   │   └── system.py                    # System/bootstrap endpoints
│   ├── agents/cv_ingestion/
│   │   ├── state.py                     # LangGraph state TypedDict
│   │   ├── nodes.py                     # Pipeline node functions
│   │   ├── graph.py                     # LangGraph workflow definition
│   │   └── schemas.py                   # Pydantic extraction schemas
│   ├── db/models/                        # SQLAlchemy ORM models
│   ├── repositories/
│   │   ├── graph_repo.py                # Apache AGE Cypher operations
│   │   └── vector_repo.py               # Qdrant vector operations
│   ├── services/
│   │   ├── age_service.py               # AGE service layer
│   │   ├── cv_ingestion_service.py      # Pipeline orchestration
│   │   ├── embedding_service.py         # Ollama embedding calls
│   │   ├── postgres_service.py          # PG health/diagnostics
│   │   └── qdrant_service.py            # Qdrant service layer
│   └── tests/integration/
│       └── test_cv_ingestion_pipeline.py
├── alembic/                              # Database migrations
├── scripts/
│   ├── init_age.sql                     # AGE graph initialization
│   └── verify_ingestion.py             # End-to-end verification
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── requirements.txt
```

## Candidate ↔ Job Scoring (OpenRouter Llama Agent)

Backend service that scores how well a candidate matches a job, combining:

* an **agent score** from a Llama model on **OpenRouter**, and
* a **vector similarity score** from Qdrant (one vector per candidate, one per job),

and saves the unified result in PostgreSQL. The same `candidate_id` and
`job_id` are used everywhere — no duplicate IDs across stores.

```
final_score = (agent_score * SCORING_AGENT_WEIGHT)
            + (vector_similarity_score * SCORING_VECTOR_WEIGHT)
```

### Environment variables

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=meta-llama/llama-3.2-3b-instruct:free
OPENROUTER_REFERER=https://paths.local
OPENROUTER_APP_TITLE=PATHS Scoring Agent

SCORING_SERVICE_ENABLED=true
SCORING_AGENT_WEIGHT=0.65
SCORING_VECTOR_WEIGHT=0.35
SCORING_MIN_RELEVANCE_THRESHOLD=0.45
SCORING_MAX_JOBS_PER_CANDIDATE=20
SCORING_MODEL_TEMPERATURE=0.1
SCORING_MODEL_MAX_TOKENS=1200
SCORING_REQUEST_TIMEOUT_SECONDS=60
SCORING_PROMPT_VERSION=v1
SCORING_ALLOW_OFFLINE_FALLBACK=true   # use deterministic scorer when no API key
```

### One-time setup

```bash
pip install -r requirements.txt        # adds httpx (already present)
alembic upgrade head                   # creates candidate_job_scores, scoring_runs, scoring_errors, scoring_criteria
```

### API endpoints (mounted under `/api/v1/scoring`)

```http
POST /api/v1/scoring/candidates/{candidate_id}/score
GET  /api/v1/scoring/candidates/{candidate_id}/scores
GET  /api/v1/scoring/candidates/{candidate_id}/jobs/{job_id}
POST /api/v1/scoring/candidates/{candidate_id}/jobs/{job_id}/score
```

#### Score a candidate against the most relevant active jobs

```bash
curl -X POST http://localhost:8000/api/v1/scoring/candidates/<candidate_uuid>/score \
     -H "Content-Type: application/json" \
     -d '{"max_jobs": 20, "force_rescore": false}'
```

#### Get saved scores ordered by `final_score DESC`

```bash
curl http://localhost:8000/api/v1/scoring/candidates/<candidate_uuid>/scores
```

#### Get the full breakdown for one (candidate, job) pair

```bash
curl http://localhost:8000/api/v1/scoring/candidates/<cid>/jobs/<jid>
```

#### Score one specific job (recruiter / admin)

```bash
curl -X POST "http://localhost:8000/api/v1/scoring/candidates/<cid>/jobs/<jid>/score" \
     -H "Content-Type: application/json" \
     -d '{"force": false}'
```

### Pipeline

1. Load the candidate's structured profile from PostgreSQL.
2. Infer the candidate's **role family** (software / data / ML / cybersecurity / …).
3. Pick the most recent active jobs and run them through the **relevance filter**
   (role family + required-skill overlap + Qdrant vector similarity ≥
   `SCORING_MIN_RELEVANCE_THRESHOLD`). Irrelevant jobs are recorded in
   `scoring_errors` as `skipped_irrelevant` and never reach the LLM.
4. For each relevant job:
   * compute Qdrant cosine similarity → 0..100;
   * **anonymize** the candidate (drop name / email / phone / photo /
     gender / age / religion / nationality / address / etc.);
   * call OpenRouter once with the JSON-only prompt + criteria;
   * retry **once** on invalid JSON, then surface a `scoring_errors` row;
   * combine `agent_score * 0.65 + vector_similarity_score * 0.35`;
   * upsert into `candidate_job_scores`;
   * best-effort `MERGE (c)-[:MATCHES_JOB {...}]->(j)` in Apache AGE.
5. Finalize the `scoring_runs` row.

### Verification

Manual SQL (after running the pipeline):

```sql
SELECT candidate_id, job_id, agent_score, vector_similarity_score, final_score, recommendation
FROM candidate_job_scores
WHERE candidate_id = '<candidate_uuid>'
ORDER BY final_score DESC;
```

AGE Cypher:

```sql
SELECT * FROM cypher('paths_graph', $$
MATCH (c:Candidate {candidate_id: '<candidate_uuid>'})-[r:MATCHES_JOB]->(j:Job)
RETURN c.candidate_id, j.job_id, r.final_score, r.recommendation
ORDER BY r.final_score DESC
$$) AS (candidate_id agtype, job_id agtype, score agtype, recommendation agtype);
```

### Tests

```bash
pytest app/tests/test_scoring_criteria.py \
       app/tests/test_scoring_prompt_builder.py \
       app/tests/test_relevance_filter.py \
       app/tests/test_vector_similarity.py \
       app/tests/test_llama_scoring_agent.py \
       app/tests/test_scoring_service.py -v
```

### Safety

* The LLM never receives candidate name, email, phone, photo, gender,
  age, religion, nationality, address or any other protected attribute —
  see `app/services/scoring/scoring_prompt_builder.py::PROTECTED_FIELDS`.
* `OPENROUTER_API_KEY` is read from environment only, never logged, and
  redacted (`***`) from any error message that could surface in HTTP
  responses.
* If OpenRouter is unreachable and `SCORING_ALLOW_OFFLINE_FALLBACK=true`,
  a deterministic local scorer based on skill overlap + experience runs
  instead, so dev / CI never blocks on network access.
* A failed graph or vector sync NEVER deletes the PostgreSQL score row —
  the row is marked `completed_with_graph_sync_failed` /
  `completed_with_vector_missing` and can be retried.

---

## Job Scraper Integration

The backend integrates the existing [`Job_Scraper-main`](../Job_Scraper-main)
directory and imports up to **5 LinkedIn / careers-page jobs every hour**
while the system is running. Each scraped job becomes one unified record
across PostgreSQL, Apache AGE, and Qdrant using the same `job_id`:

```
PostgreSQL jobs.id == Apache AGE Job.job_id == Qdrant point id == Qdrant payload.job_id
```

### Environment variables

```env
JOB_SCRAPER_ENABLED=false              # opt-in; requires Playwright + Firefox
JOB_SCRAPER_INTERVAL_MINUTES=60        # how often the scheduler fires
JOB_SCRAPER_BATCH_SIZE=5               # hard cap on jobs imported per run
JOB_SCRAPER_RUN_ON_STARTUP=false
JOB_SCRAPER_SOURCE=linkedin
JOB_SCRAPER_TIMEOUT_SECONDS=120        # whole-run timeout (browser crashes never hang the API)
JOB_SCRAPER_MAX_PAGES_PER_RUN=1
JOB_SCRAPER_LOG_LEVEL=INFO
JOB_SCRAPER_MODULE_PATH=../Job_Scraper-main
JOB_SCRAPER_DATA_FILE=../Job_Scraper-main/data/Data.xlsx
JOB_SCRAPER_COMPANIES_PER_RUN=8        # how many companies to visit per run
JOB_SCRAPER_HEADLESS=true
JOB_SCRAPER_STUB=false                 # set true for tests / dev without Playwright
JOB_SCRAPER_LOCK_NAME=paths_job_scraper_hourly_import
QDRANT_COLLECTION_JOBS=paths_jobs      # spec alias for the unified job collection
EMBEDDING_MODEL_NAME=nomic-embed-text  # spec alias for EMBEDDING_MODEL
```

### One-time setup

```bash
# Install runtime deps (apscheduler is already in requirements.txt)
pip install -r requirements.txt

# Optional — only needed when JOB_SCRAPER_STUB=false
pip install pandas openpyxl playwright playwright-stealth
playwright install firefox

# Apply the new tables
alembic upgrade head
```

### Manual import (admin endpoints)

```bash
# Trigger one immediate import run
curl -X POST http://localhost:8000/api/v1/admin/job-import/run-once \
     -H "Content-Type: application/json" \
     -d '{"limit": 5, "source": "linkedin"}'

# Scheduler / last-run summary
curl http://localhost:8000/api/v1/admin/job-import/status

# Recent import-run history
curl http://localhost:8000/api/v1/admin/job-import/history?limit=10
```

### Hourly behaviour

Once `JOB_SCRAPER_ENABLED=true` the FastAPI lifespan starts an
`AsyncIOScheduler` that runs `JobImportService.run_import` every
`JOB_SCRAPER_INTERVAL_MINUTES`. Multi-worker deploys are made safe by
the PostgreSQL advisory lock `paths_job_scraper_hourly_import` — only
the worker that wins the lock runs the import; others log
`status=locked` and exit cleanly.

The pipeline:

1. Acquire advisory lock.
2. Create `job_import_runs` row.
3. Ask the adapter for raw jobs (capped at `JOB_SCRAPER_BATCH_SIZE`).
4. Normalize + validate + dedup.
5. For each valid job:
   * upsert company, job, skills, requirements, responsibilities (one transaction)
   * sync to Apache AGE (`upsert_job_node`, `REQUIRES_SKILL`, `POSTED`)
   * sync to Qdrant (one point, id == jobs.id)
   * update `jobs.graph_sync_status` / `jobs.vector_sync_status`
6. Persist the new company offset in `job_scraper_state`.
7. Finalize the run row (`success` / `partial` / `failed`).

Failures in graph or vector sync are recorded but **never delete the
PostgreSQL row** — the next run (or `POST /api/v1/admin/sync/job/{id}/retry`)
recovers them.

### Verification

```bash
python scripts/verify_job_import_sync.py --limit 5
```

Expected:

```
PASS job_id=… title='Senior Backend Engineer' postgres=True graph=True qdrant=True vector_count=1
```

### Tests

```bash
pytest app/tests/test_job_normalizer.py \
       app/tests/test_job_deduplication.py \
       app/tests/test_skill_dictionary.py \
       app/tests/test_scraper_adapter.py -v

# Live integration test (skipped automatically when services aren't running)
pytest app/tests/integration/test_job_import_pipeline.py -v
```

### Safety notes

* The scheduler is **disabled by default**; nothing scrapes until you
  flip `JOB_SCRAPER_ENABLED=true`.
* The adapter never bypasses LinkedIn login, CAPTCHA, or rate limits.
  It walks the configured company list slowly via DuckDuckGo + the
  existing per-platform parsers (Lever, Greenhouse, Zoho, SmartRecruiters,
  Workday) provided by `Job_Scraper-main`.
* All scraper failures are caught and recorded in `job_import_errors`.
  One broken job never fails the whole run.
* No secrets are written to logs — `database_health_service` already
  redacts `POSTGRES_PASSWORD` / `QDRANT_API_KEY` in `_safe_error`.

---

## Known Limitations

1. **Ollama model pull required**: The LLM and embedding models must be manually pulled into the Ollama container after first start.
2. **OCR not implemented**: Scanned PDFs without text layers will fail extraction. Only text-based PDFs are supported.
3. **No authentication**: API endpoints are unprotected in the current version.
4. **AGE parameterized queries**: Apache AGE's Cypher parameter handling varies by driver; the current implementation uses string-substituted Cypher queries with care.
5. **Single-threaded pipeline**: Each CV is processed sequentially through the LangGraph pipeline. For production, consider adding a task queue (Celery/RQ).
