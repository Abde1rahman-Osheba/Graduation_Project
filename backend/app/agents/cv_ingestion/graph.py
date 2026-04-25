from langgraph.graph import StateGraph, END
from app.agents.cv_ingestion.state import CVIngestionState
from app.agents.cv_ingestion.nodes import (
    load_document, extract_structured_candidate_data, normalize_entities,
    persist_postgres, project_to_age, chunk_document, embed_chunks, upsert_qdrant,
    sync_unified_candidate, finalize_job, handle_failure,
)

def create_ingestion_graph():
    workflow = StateGraph(CVIngestionState)

    workflow.add_node("load_document", load_document)
    workflow.add_node("extract_structured", extract_structured_candidate_data)
    workflow.add_node("normalize", normalize_entities)
    workflow.add_node("persist_postgres", persist_postgres)
    workflow.add_node("project_age", project_to_age)
    workflow.add_node("chunk", chunk_document)
    workflow.add_node("embed", embed_chunks)
    workflow.add_node("upsert_vector", upsert_qdrant)
    workflow.add_node("sync_unified_candidate", sync_unified_candidate)
    workflow.add_node("finalize", finalize_job)
    workflow.add_node("handle_failure", handle_failure)

    # Entry point
    workflow.set_entry_point("load_document")

    # Routing conditionally based on status
    def check_failure(state: CVIngestionState):
        if state.get("status") == "failed":
            return "handle_failure"
        return "next"

    workflow.add_conditional_edges("load_document", check_failure, {"handle_failure": "handle_failure", "next": "extract_structured"})
    workflow.add_conditional_edges("extract_structured", check_failure, {"handle_failure": "handle_failure", "next": "normalize"})
    workflow.add_conditional_edges("normalize", check_failure, {"handle_failure": "handle_failure", "next": "persist_postgres"})
    workflow.add_conditional_edges("persist_postgres", check_failure, {"handle_failure": "handle_failure", "next": "project_age"})
    workflow.add_conditional_edges("project_age", check_failure, {"handle_failure": "handle_failure", "next": "chunk"})
    workflow.add_conditional_edges("chunk", check_failure, {"handle_failure": "handle_failure", "next": "embed"})
    workflow.add_conditional_edges("embed", check_failure, {"handle_failure": "handle_failure", "next": "upsert_vector"})
    # The unified candidate sync is intentionally *non-blocking*: even if it
    # records a sync failure, we still advance to `finalize` so the
    # PostgreSQL data and the legacy chunk vectors are preserved.
    workflow.add_edge("upsert_vector", "sync_unified_candidate")
    workflow.add_edge("sync_unified_candidate", "finalize")

    workflow.add_edge("finalize", END)
    workflow.add_edge("handle_failure", END)

    return workflow.compile()

ingestion_app = create_ingestion_graph()
