"""Standalone Retrieval-Augmented Generation (RAG) package.

Pipeline: PDF → extract → chunk → embed (Ollama nomic-embed-text) →
Chroma → retrieve → answer (Ollama llama3.2 via OllamaGateway).

This package is intentionally separate from StudyPlan / scheduling services.
"""

from app.rag.rag_service import RagAnswer, RagError, RagService, RagSource

__all__ = ["RagAnswer", "RagError", "RagService", "RagSource"]
