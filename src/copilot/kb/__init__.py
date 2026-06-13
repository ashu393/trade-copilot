"""Knowledge-base retrieval (RAG) over the policy/glossary documents."""

from .loader import KBChunk, load_kb_chunks
from .retriever import KBRetriever, RetrievedChunk

__all__ = ["KBChunk", "load_kb_chunks", "KBRetriever", "RetrievedChunk"]
