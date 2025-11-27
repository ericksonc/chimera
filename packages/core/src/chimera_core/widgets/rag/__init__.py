"""RAG (Retrieval-Augmented Generation) components.

This package provides modular RAG functionality:
- Document chunking with context-aware splitting
- Voyage AI embeddings generation
- ChromaDB vector storage and retrieval
- Global registry for cross-collection deduplication
"""

from .chunker import Chunk, DocumentChunker
from .embeddings import EmbeddingResult, VoyageEmbeddingService
from .global_registry import ChunkParams, GlobalRAGRegistry, RegistryEntry
from .vector_store import SearchResult, VectorStore

__all__ = [
    "DocumentChunker",
    "Chunk",
    "VoyageEmbeddingService",
    "EmbeddingResult",
    "VectorStore",
    "SearchResult",
    "GlobalRAGRegistry",
    "ChunkParams",
    "RegistryEntry",
]
