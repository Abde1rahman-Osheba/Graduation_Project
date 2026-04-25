"""PATHS Backend — Organization-side matching, anonymization & outreach.

Inspired by the `outreach-agent-main/` BDR/Sales Google-ADK project but
implemented with the existing PATHS infrastructure (FastAPI, SQLAlchemy,
the unified PostgreSQL ↔ Apache AGE ↔ Qdrant layer, and the OpenRouter
LlamaScoringAgent built in earlier PRs).

Submodules:

  * `organization_llm_provider`                — OpenRouter | Ollama
  * `organization_job_intake_agent`            — job intake → PG → AGE → Qdrant
  * `organization_bias_guardrail_service`      — blind candidate IDs + anonymization
  * `organization_candidate_search_service`    — Path A discovery
  * `organization_csv_candidate_import_service`— Path B import (SSRF-safe)
  * `organization_ranking_service`             — score + rank candidates
  * `organization_outreach_prompt_builder`     — recruitment-email prompt
  * `organization_outreach_service`            — draft / approve / send
  * `organization_streaming_service`           — SSE wrapper for LLM streaming
  * `organization_mcp_service`                 — Calendar / Gmail MCP stubs
  * `organization_matching_service`            — Path A + Path B orchestrator
"""
