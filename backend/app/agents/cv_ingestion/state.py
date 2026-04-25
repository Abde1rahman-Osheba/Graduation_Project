from typing import TypedDict, List, Optional, Dict, Any

class CVIngestionState(TypedDict):
    job_id: str
    candidate_id: Optional[str]
    document_id: Optional[str]
    file_path: str
    raw_text: Optional[str]
    structured_candidate: Optional[Dict[str, Any]]
    normalized_candidate: Optional[Dict[str, Any]]
    chunks: Optional[List[str]]
    embeddings: Optional[List[List[float]]]
    errors: List[str]
    status: str
    stage: str
