"""Global RAG Embedding Registry for cross-collection deduplication.

This module provides a system-wide registry that tracks which files have been
embedded with which parameters, enabling reuse of embeddings across different
RAG collections that reference the same underlying files.

Architecture:
- SQLite database in ~/.chimera/rag_global_registry.db
- Tracks: (absolute_path, content_hash, chunk_params_hash) → (collection, chunk_ids)
- Enables cross-collection chunk reuse without redundant embedding API calls
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ChunkParams:
    """Parameters that affect chunking and must match for reuse."""

    chunk_min_tokens: int
    chunk_max_tokens: int

    def compute_hash(self) -> str:
        """Compute hash of chunk parameters.

        Returns:
            SHA256 hex string (64 characters)
        """
        params_str = f"{self.chunk_min_tokens}:{self.chunk_max_tokens}"
        return hashlib.sha256(params_str.encode("utf-8")).hexdigest()


@dataclass
class RegistryEntry:
    """Entry in global RAG registry."""

    absolute_path: str
    content_hash: str
    chunk_params_hash: str
    collection_name: str
    chunk_count: int
    chunk_ids: List[str]  # List of ChromaDB chunk IDs


class GlobalRAGRegistry:
    """Global registry for RAG embedding deduplication.

    This registry enables cross-collection embedding reuse by tracking which files
    have been embedded with which parameters. When a new collection is initialized,
    it can query this registry to find existing embeddings instead of making
    redundant API calls.

    Key Insights:
    - ChromaDB collections are isolated by design (one per base_path)
    - Same file in different collections has different relative paths
    - But file content and chunking params are what matter for embeddings
    - This registry bridges collections using absolute paths + content hashes

    Usage:
        registry = GlobalRAGRegistry()

        # Check if file has been embedded before
        entry = registry.lookup(
            absolute_path="/path/to/file.md",
            content_hash="abc123...",
            chunk_params=ChunkParams(400, 600)
        )

        if entry:
            # Reuse existing chunks from entry.collection_name
            vector_store.copy_chunks(...)
        else:
            # Embed file and register
            registry.register(...)
    """

    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize global RAG registry.

        Args:
            registry_path: Path to SQLite database
                (defaults to ~/.chimera/rag_global_registry.db)
        """
        if registry_path is None:
            chimera_dir = Path.home() / ".chimera"
            chimera_dir.mkdir(parents=True, exist_ok=True)
            registry_path = chimera_dir / "rag_global_registry.db"

        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(str(self.registry_path))
        try:
            cursor = conn.cursor()

            # Create main registry table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rag_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    absolute_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    chunk_params_hash TEXT NOT NULL,
                    collection_name TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    chunk_ids TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(absolute_path, content_hash, chunk_params_hash)
                )
            """)

            # Create index for fast lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_lookup
                ON rag_registry(absolute_path, content_hash, chunk_params_hash)
            """)

            # Create index for collection cleanup queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_collection
                ON rag_registry(collection_name)
            """)

            conn.commit()
        finally:
            conn.close()

    def lookup(
        self, absolute_path: str, content_hash: str, chunk_params: ChunkParams
    ) -> Optional[RegistryEntry]:
        """Look up existing embeddings for a file.

        Args:
            absolute_path: Absolute path to file
            content_hash: SHA256 hash of file content
            chunk_params: Chunking parameters

        Returns:
            RegistryEntry if found, None otherwise
        """
        chunk_params_hash = chunk_params.compute_hash()

        conn = sqlite3.connect(str(self.registry_path))
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT collection_name, chunk_count, chunk_ids
                FROM rag_registry
                WHERE absolute_path = ?
                  AND content_hash = ?
                  AND chunk_params_hash = ?
                LIMIT 1
            """,
                (absolute_path, content_hash, chunk_params_hash),
            )

            row = cursor.fetchone()
            if row is None:
                return None

            collection_name, chunk_count, chunk_ids_json = row
            chunk_ids = json.loads(chunk_ids_json)

            return RegistryEntry(
                absolute_path=absolute_path,
                content_hash=content_hash,
                chunk_params_hash=chunk_params_hash,
                collection_name=collection_name,
                chunk_count=chunk_count,
                chunk_ids=chunk_ids,
            )
        finally:
            conn.close()

    def register(
        self,
        absolute_path: str,
        content_hash: str,
        chunk_params: ChunkParams,
        collection_name: str,
        chunk_ids: List[str],
    ) -> None:
        """Register new embeddings in global registry.

        Args:
            absolute_path: Absolute path to file
            content_hash: SHA256 hash of file content
            chunk_params: Chunking parameters used
            collection_name: ChromaDB collection where chunks are stored
            chunk_ids: List of chunk IDs in ChromaDB
        """
        chunk_params_hash = chunk_params.compute_hash()
        chunk_ids_json = json.dumps(chunk_ids)

        conn = sqlite3.connect(str(self.registry_path))
        try:
            cursor = conn.cursor()

            # Use INSERT OR REPLACE to handle updates
            cursor.execute(
                """
                INSERT OR REPLACE INTO rag_registry
                (absolute_path, content_hash, chunk_params_hash,
                 collection_name, chunk_count, chunk_ids, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    absolute_path,
                    content_hash,
                    chunk_params_hash,
                    collection_name,
                    len(chunk_ids),
                    chunk_ids_json,
                ),
            )

            conn.commit()
        finally:
            conn.close()

    def get_entries_by_collection(self, collection_name: str) -> List[RegistryEntry]:
        """Get all registry entries for a specific collection.

        Useful for cleanup operations when a collection is deleted.

        Args:
            collection_name: ChromaDB collection name

        Returns:
            List of RegistryEntry objects
        """
        conn = sqlite3.connect(str(self.registry_path))
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT absolute_path, content_hash, chunk_params_hash,
                       collection_name, chunk_count, chunk_ids
                FROM rag_registry
                WHERE collection_name = ?
            """,
                (collection_name,),
            )

            entries = []
            for row in cursor.fetchall():
                (
                    abs_path,
                    content_hash,
                    chunk_params_hash,
                    coll_name,
                    chunk_count,
                    chunk_ids_json,
                ) = row
                entries.append(
                    RegistryEntry(
                        absolute_path=abs_path,
                        content_hash=content_hash,
                        chunk_params_hash=chunk_params_hash,
                        collection_name=coll_name,
                        chunk_count=chunk_count,
                        chunk_ids=json.loads(chunk_ids_json),
                    )
                )

            return entries
        finally:
            conn.close()

    def remove_by_collection(self, collection_name: str) -> int:
        """Remove all registry entries for a collection.

        Call this when a ChromaDB collection is deleted to keep registry clean.

        Args:
            collection_name: ChromaDB collection name

        Returns:
            Number of entries removed
        """
        conn = sqlite3.connect(str(self.registry_path))
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                DELETE FROM rag_registry
                WHERE collection_name = ?
            """,
                (collection_name,),
            )

            deleted_count = cursor.rowcount
            conn.commit()

            return deleted_count
        finally:
            conn.close()

    def stats(self) -> Dict[str, int]:
        """Get registry statistics.

        Returns:
            Dict with counts: total_entries, total_collections, total_files
        """
        conn = sqlite3.connect(str(self.registry_path))
        try:
            cursor = conn.cursor()

            # Total entries
            cursor.execute("SELECT COUNT(*) FROM rag_registry")
            total_entries = cursor.fetchone()[0]

            # Unique collections
            cursor.execute("SELECT COUNT(DISTINCT collection_name) FROM rag_registry")
            total_collections = cursor.fetchone()[0]

            # Unique files (by absolute_path)
            cursor.execute("SELECT COUNT(DISTINCT absolute_path) FROM rag_registry")
            total_files = cursor.fetchone()[0]

            return {
                "total_entries": total_entries,
                "total_collections": total_collections,
                "total_files": total_files,
            }
        finally:
            conn.close()
