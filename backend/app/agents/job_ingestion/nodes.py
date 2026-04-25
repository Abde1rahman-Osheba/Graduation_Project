"""
PATHS Backend - Job Ingestion Graph Nodes
"""
import re
import json
import uuid
import hashlib
import logging
from app.agents.job_ingestion.state import JobIngestionState
from app.adapters.job_sources.generic_html import GenericHtmlListingAdapter
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.repositories import graph_repo

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_service():
    """Lazy import to break circular dependency: nodes -> service -> graph -> nodes."""
    from app.services.job_ingestion_service import JobIngestionService
    return JobIngestionService()


from app.adapters.job_sources.telegram_channel import TelegramChannelAdapter

def get_adapter(source_type: str):
    if source_type == "generic_html":
        return GenericHtmlListingAdapter()
    elif source_type == "telegram_channel":
        return TelegramChannelAdapter()
    return None

async def fetch_jobs_node(state: JobIngestionState) -> dict:
    adapter = get_adapter(state["source_type"])
    if not adapter:
        return {"errors": [{"stage": "fetch", "error_type": "AdapterNotFound", "error_message": f"Adapter {state['source_type']} not found."}]}
    
    raw_items = []
    
    for url in state["target_urls"][:state["max_pages"]]:
        raw = await adapter.fetch(url)
        raw_items.append(raw)
        
    return {"raw_items": raw_items}


async def parse_source_node(state: JobIngestionState) -> dict:
    adapter = get_adapter(state["source_type"])
    if not adapter:
        return {}
    
    all_parsed = []
    errors = []
    for raw in state["raw_items"]:
        try:
            parsed = await adapter.parse(raw)
            if parsed:
                all_parsed.extend(parsed)
        except Exception as e:
            errors.append({"stage": "parse", "error_type": "ParseError", "error_message": str(e), "details_jsonb": {"url": raw.get("source_url")}})
            
    return {"normalized_items": all_parsed, "errors": errors}

async def normalize_job_node(state: JobIngestionState) -> dict:
    for item in state["normalized_items"]:
        hash_input = f"{item.get('company_name', '')}_{item.get('title', '')}_{item.get('source_url', '')}".lower()
        item["canonical_hash"] = hashlib.sha256(hash_input.encode()).hexdigest()
    return {}

async def extract_skills_node(state: JobIngestionState) -> dict:
    """Extract skills from each normalized job using Ollama LLM."""
    items = state.get("normalized_items", [])
    if not items:
        return {}

    try:
        from langchain_ollama import ChatOllama
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatOllama(
            model=settings.ollama_llm_model,
            base_url=settings.ollama_base_url,
            temperature=0.0,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an expert recruiter. Extract ONLY the technical skills "
             "and tools mentioned or required in the job posting below. "
             "Return a JSON array of lowercase skill strings. "
             "Example: [\"python\", \"aws\", \"docker\", \"react\"]. "
             "Return ONLY the JSON array, no explanation."),
            ("human", "Job Title: {title}\n\nDescription:\n{description}")
        ])

        chain = prompt | llm

        for item in items:
            desc = item.get("description_text", "") or ""
            title = item.get("title", "") or ""
            if not desc and not title:
                item["extracted_skills"] = []
                continue

            # Truncate very long descriptions to avoid token limits
            truncated_desc = desc[:3000]

            try:
                result = chain.invoke({"title": title, "description": truncated_desc})
                raw_text = result.content.strip()

                # Parse JSON array from LLM response
                # Handle cases where LLM wraps in markdown code block
                json_match = re.search(r'\[.*?\]', raw_text, re.DOTALL)
                if json_match:
                    skills = json.loads(json_match.group())
                    # Normalize: lowercase, strip, deduplicate
                    seen = set()
                    clean_skills = []
                    for s in skills:
                        if isinstance(s, str):
                            normalized = s.strip().lower()
                            if normalized and normalized not in seen:
                                seen.add(normalized)
                                clean_skills.append(normalized)
                    item["extracted_skills"] = clean_skills
                    logger.info("Extracted %d skills for job '%s'", len(clean_skills), title[:40])
                else:
                    item["extracted_skills"] = []
                    logger.warning("No JSON array found in LLM response for job '%s'", title[:40])
            except Exception as e:
                logger.error("LLM skill extraction failed for job '%s': %s", title[:40], str(e))
                item["extracted_skills"] = []

    except Exception as e:
        logger.error("Skill extraction setup failed: %s", str(e))
        # Don't block the pipeline — just skip skill extraction
        for item in items:
            item.setdefault("extracted_skills", [])

    return {}

async def deduplicate_job_node(state: JobIngestionState) -> dict:
    service = _get_service()
    duplicates_hashes = await service.identify_duplicates(state["normalized_items"])
    return {"stats": {"duplicate_hashes": duplicates_hashes}}

async def persist_job_node(state: JobIngestionState) -> dict:
    service = _get_service()
    dup_hashes = state.get("stats", {}).get("duplicate_hashes", [])
    
    items_to_persist = [item for item in state["normalized_items"] if item.get("canonical_hash") not in dup_hashes]
    
    if state["run_id"]:
        persisted_ids, errors = await service.persist_jobs(state["run_id"], items_to_persist)
        await service.persist_raw_items(state["run_id"], state["raw_items"])
        return {"persisted_job_ids": persisted_ids, "errors": errors}
    return {}

async def sync_unified_jobs_node(state: JobIngestionState) -> dict:
    """For each persisted job, run the spec-compliant unified sync.

    This produces exactly one Qdrant point per job in
    `QDRANT_JOB_COLLECTION` (`paths_jobs`) using the PostgreSQL `job_id`
    as both the point ID and the payload `job_id`.
    """
    persisted_ids = state.get("persisted_job_ids", [])
    if not persisted_ids:
        return {}

    db = SessionLocal()
    try:
        from app.services.job_sync_service import sync_job_full

        for jid in persisted_ids:
            try:
                sync_job_full(db, jid)
            except Exception as exc:  # noqa: BLE001
                logger.exception("unified job sync failed for %s", jid)
                # Don't break the whole run; recorded in db_sync_status
                _ = exc
    finally:
        db.close()
    return {}


async def project_to_age_node(state: JobIngestionState) -> dict:
    """Project persisted jobs, their skills, and company relationships into Apache AGE graph."""
    items = state.get("normalized_items", [])
    persisted_ids = state.get("persisted_job_ids", [])

    if not items:
        return {}

    db = SessionLocal()
    try:
        graph_repo.init_graph(db)

        for idx, item in enumerate(items):
            job_id = str(persisted_ids[idx]) if idx < len(persisted_ids) else str(uuid.uuid4())
            title = item.get("title", "Unknown")
            company = item.get("company_name", "Unknown Company")
            seniority = item.get("seniority_level")
            experience = item.get("experience_level")

            # Project Job node
            graph_repo.project_job(db, job_id, title, company, seniority, experience)

            # Project Company node + POSTED_BY edge
            if company and company != "Unknown Company":
                graph_repo.project_job_company(db, job_id, company)

            # Project Skill nodes + REQUIRES_SKILL edges
            skills = item.get("extracted_skills", [])
            for skill_name in skills:
                graph_repo.project_job_skill(db, job_id, skill_name)

            logger.info("Projected job '%s' with %d skills to AGE graph", title[:40], len(skills))

        db.commit()
        logger.info("AGE projection complete for %d jobs", len(items))
    except Exception as e:
        db.rollback()
        logger.exception("AGE projection error: %s", str(e))
        return {"errors": [{"stage": "project_age", "error_type": "AGEProjectionError", "error_message": str(e)}]}
    finally:
        db.close()

    return {}

async def finalize_run_node(state: JobIngestionState) -> dict:
    if state["run_id"]:
        service = _get_service()
        await service.finalize_run(state)
    return {}

async def handle_error_node(state: JobIngestionState) -> dict:
    if state["run_id"] and state["errors"]:
        service = _get_service()
        await service.save_errors(state["run_id"], state["errors"])
    return {}
