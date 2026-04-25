"""
PATHS Backend — Embedding service.

Uses Ollama's local embedding model (nomic-embed-text) for vector generation.
"""

from typing import List
from langchain_ollama import OllamaEmbeddings
from app.core.config import get_settings

settings = get_settings()


def get_embeddings_service() -> OllamaEmbeddings:
    """Return an OllamaEmbeddings instance configured from settings."""
    return OllamaEmbeddings(
        model=settings.ollama_embed_model,
        base_url=settings.ollama_base_url,
    )


def embed_documents(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts using the local Ollama embedding model."""
    if not texts:
        return []
    embeddings = get_embeddings_service()
    return embeddings.embed_documents(texts)


def embed_query(text: str) -> List[float]:
    """Embed a single query text."""
    embeddings = get_embeddings_service()
    return embeddings.embed_query(text)
