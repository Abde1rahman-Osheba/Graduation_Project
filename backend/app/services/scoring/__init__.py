"""PATHS Backend — Candidate-Job scoring service package.

Implements the spec described in
`PATHS_Candidate_Job_Scoring_Service_Cursor_Instructions.md`.

  * `scoring_criteria.py`         — default 6-criterion breakdown
  * `scoring_prompt_builder.py`   — anonymized JSON-only prompt
  * `llama_scoring_agent.py`      — OpenRouter HTTP wrapper
  * `vector_similarity_service.py`— Qdrant cosine similarity (one vec per entity)
  * `relevance_filter_service.py` — role-family + skill-overlap gate
  * `scoring_service.py`          — orchestrator (PG → AGE → Qdrant → APIs)
"""
