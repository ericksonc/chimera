"""ChromaDB vector store for RAG embeddings.

This module provides persistence and retrieval of document embeddings using ChromaDB.
Collections are organized by content hash for automatic invalidation and cross-thread reuse.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None


@dataclass
class SearchResult:
    """Result from vector similarity search."""

    content: str
    score: float  # Similarity score (higher = more similar)
    metadata: Dict[str, Any]
    chunk_index: int


class VectorStore:
    """ChromaDB-based vector store for document embeddings.

    Features:
    - Global collection per base_path for knowledge reuse
    - Per-file hash tracking for incremental updates
    - Query-time filtering by file paths
    - Lazy loading (check if file embeddings exist before generating)
    - Persistent storage on disk
    - Age-based cleanup of old collections
    """

    def __init__(self, persist_directory: Optional[str] = None, collection_prefix: str = "rag_"):
        """Initialize vector store.

        Args:
            persist_directory: Directory for ChromaDB storage
                (defaults to data/chromadb)
            collection_prefix: Prefix for collection names
                (default: "rag_" for global collections per base_path)
        """
        if chromadb is None:
            raise ImportError("chromadb is not installed. Install it with: pip install chromadb")

        # Default to data/chromadb
        if persist_directory is None:
            persist_directory = os.getenv("CHROMADB_DIR", "data/chromadb")

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_prefix = collection_prefix

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False, allow_reset=False),
        )

    # ========================================================================
    # Global Collection Methods (Per base_path)
    # ========================================================================

    def get_collection_name(self, base_path: str) -> str:
        """Get collection name from base_path.

        Args:
            base_path: Absolute path to project directory

        Returns:
            Collection name string (e.g., "rag_a1b2c3d4")
        """
        import hashlib

        path_hash = hashlib.sha256(base_path.encode("utf-8")).hexdigest()[:16]
        return f"{self.collection_prefix}{path_hash}"

    def get_or_create_collection(self, base_path: str):
        """Get or create collection for a base_path.

        Args:
            base_path: Absolute path to project directory

        Returns:
            ChromaDB collection object
        """
        collection_name = self.get_collection_name(base_path)

        collection_metadata = {
            "base_path": base_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return self.client.get_or_create_collection(
            name=collection_name, metadata=collection_metadata
        )

    def get_file_hashes(self, base_path: str) -> Dict[str, str]:
        """Get all file hashes currently stored in collection.

        Args:
            base_path: Absolute path to project directory

        Returns:
            Dict mapping file_path to file_hash
        """
        collection_name = self.get_collection_name(base_path)

        try:
            collection = self.client.get_collection(name=collection_name)
        except Exception:
            return {}

        # Get all items with their metadata
        # We need to get unique file_path + file_hash combinations
        results = collection.get(include=["metadatas"])

        file_hashes = {}
        if results and results.get("metadatas"):
            for metadata in results["metadatas"]:
                file_path = metadata.get("file_path")
                file_hash = metadata.get("file_hash")
                if file_path and file_hash:
                    file_hashes[file_path] = file_hash

        return file_hashes

    def delete_file_chunks(self, base_path: str, file_path: str) -> int:
        """Delete all chunks for a specific file.

        Args:
            base_path: Absolute path to project directory
            file_path: Relative path to file within base_path

        Returns:
            Number of chunks deleted
        """
        collection = self.get_or_create_collection(base_path)

        # Get all chunk IDs for this file
        results = collection.get(where={"file_path": file_path}, include=["metadatas"])

        if not results or not results.get("ids"):
            return 0

        chunk_ids = results["ids"]
        collection.delete(ids=chunk_ids)

        return len(chunk_ids)

    def store_file_chunks(
        self,
        base_path: str,
        file_path: str,
        file_hash: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Store chunks for a single file.

        Args:
            base_path: Absolute path to project directory
            file_path: Relative path to file within base_path
            file_hash: SHA256 hash of file content
            chunks: List of text chunks for this file
            embeddings: List of embedding vectors
            metadatas: Optional metadata for each chunk

        Raises:
            ValueError: If chunks and embeddings lengths don't match
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have same length"
            )

        # Skip if no chunks (file too small or no content)
        if len(chunks) == 0:
            return

        collection = self.get_or_create_collection(base_path)

        # Generate unique IDs for this file's chunks
        # Use file_path + chunk_index for deterministic IDs
        import hashlib

        file_id_prefix = hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:8]
        ids = [f"{file_id_prefix}_{i}" for i in range(len(chunks))]

        # Ensure metadata includes file_path and file_hash
        if metadatas is None:
            metadatas = []

        for i, meta in enumerate(metadatas if metadatas else [{}] * len(chunks)):
            meta["file_path"] = file_path
            meta["file_hash"] = file_hash
            if "chunk_index" not in meta:
                meta["chunk_index"] = i

        # Store in ChromaDB
        collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

    def get_chunks_by_indices(
        self, base_path: str, file_path: str, chunk_indices: List[int]
    ) -> Dict[int, str]:
        """Get specific chunks by their indices within a file.

        Args:
            base_path: Absolute path to project directory
            file_path: Relative path to file within base_path
            chunk_indices: List of chunk indices to retrieve

        Returns:
            Dict mapping chunk_index → chunk_content
        """
        collection_name = self.get_collection_name(base_path)

        try:
            collection = self.client.get_collection(name=collection_name)
        except Exception:
            return {}

        # Get all chunks for this file
        results = collection.get(where={"file_path": file_path}, include=["documents", "metadatas"])

        if not results or not results.get("documents"):
            return {}

        # Build mapping of chunk_index → content
        chunk_map = {}
        documents = results["documents"]
        metadatas = results["metadatas"] if results.get("metadatas") else [{}] * len(documents)

        for doc, metadata in zip(documents, metadatas):
            idx = metadata.get("chunk_index", -1)
            if idx in chunk_indices:
                chunk_map[idx] = doc

        return chunk_map

    def copy_chunks(
        self,
        source_collection_name: str,
        source_chunk_ids: List[str],
        target_base_path: str,
        target_file_path: str,
        target_file_hash: str,
    ) -> int:
        """Copy chunks from source collection to target collection.

        This enables cross-collection reuse of embeddings without redundant
        API calls. Used by global RAG registry for deduplication.

        Args:
            source_collection_name: Source ChromaDB collection name
            source_chunk_ids: List of chunk IDs to copy from source
            target_base_path: Absolute path to target project directory
            target_file_path: Relative path within target base_path
            target_file_hash: SHA256 hash of target file content

        Returns:
            Number of chunks copied

        Raises:
            ValueError: If source collection doesn't exist
            ValueError: If source chunks don't exist
        """
        # Get source collection
        try:
            source_collection = self.client.get_collection(name=source_collection_name)
        except Exception as e:
            raise ValueError(f"Source collection '{source_collection_name}' not found") from e

        # Retrieve chunks from source
        source_results = source_collection.get(
            ids=source_chunk_ids, include=["embeddings", "documents", "metadatas"]
        )

        # Check if results are empty (handle numpy array ambiguity)
        embeddings = source_results.get("embeddings")
        if not source_results or embeddings is None or len(embeddings) == 0:
            raise ValueError(f"No chunks found in source collection for IDs: {source_chunk_ids}")

        # Extract data
        embeddings = source_results["embeddings"]
        documents = source_results["documents"]
        source_metadatas = (
            source_results["metadatas"]
            if source_results.get("metadatas")
            else [{}] * len(documents)
        )

        # Get or create target collection
        target_collection = self.get_or_create_collection(target_base_path)

        # Generate new IDs for target collection
        # Use target file_path + chunk_index for deterministic IDs
        import hashlib

        file_id_prefix = hashlib.sha256(target_file_path.encode("utf-8")).hexdigest()[:8]

        # Build new metadata with updated file_path and file_hash
        new_ids = []
        new_metadatas = []

        for i, source_meta in enumerate(source_metadatas):
            # Preserve chunk_index and other metadata
            new_meta = source_meta.copy()
            new_meta["file_path"] = target_file_path
            new_meta["file_hash"] = target_file_hash

            chunk_index = new_meta.get("chunk_index", i)
            new_id = f"{file_id_prefix}_{chunk_index}"

            new_ids.append(new_id)
            new_metadatas.append(new_meta)

        # Add to target collection
        target_collection.add(
            ids=new_ids, embeddings=embeddings, documents=documents, metadatas=new_metadatas
        )

        return len(new_ids)

    def search(
        self,
        base_path: str,
        query_embedding: List[float],
        file_paths: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Search for similar chunks, optionally filtered by file paths.

        Args:
            base_path: Absolute path to project directory
            query_embedding: Query embedding vector
            file_paths: Optional list of file paths to search within (None = search all)
            top_k: Number of results to return

        Returns:
            List of SearchResult objects, sorted by relevance
        """
        collection_name = self.get_collection_name(base_path)

        try:
            collection = self.client.get_collection(name=collection_name)
        except Exception:
            return []

        # Build where filter if file_paths provided
        where_filter = None
        if file_paths is not None:
            where_filter = {"file_path": {"$in": file_paths}}

        # Query ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding], where=where_filter, n_results=top_k
        )

        # Parse results
        search_results = []
        if results["documents"] and len(results["documents"]) > 0:
            documents = results["documents"][0]
            distances = results["distances"][0]
            metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(documents)

            for doc, distance, metadata in zip(documents, distances, metadatas):
                # Convert distance to similarity score
                # ChromaDB returns L2 distance, convert to similarity
                score = 1.0 / (1.0 + distance)

                search_results.append(
                    SearchResult(
                        content=doc,
                        score=score,
                        metadata=metadata,
                        chunk_index=metadata.get("chunk_index", -1),
                    )
                )

        return search_results

    # ========================================================================
    # Legacy Methods (Deprecated - kept for backward compatibility)
    # ========================================================================

    def store_embeddings_by_content(
        self,
        content_hash: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        document_count: Optional[int] = None,
        total_chars: Optional[int] = None,
    ) -> None:
        """Store document chunks and their embeddings by content hash.

        Args:
            content_hash: SHA256 hash of document set
            chunks: List of text chunks
            embeddings: List of embedding vectors
            metadatas: Optional metadata for each chunk (must include file_hash)
            document_count: Number of documents in set (for metadata)
            total_chars: Total character count (for metadata)

        Raises:
            ValueError: If chunks and embeddings lengths don't match
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have same length"
            )

        collection_name = self.get_collection_name_by_content(content_hash)

        # Collection-level metadata
        collection_metadata = {
            "content_hash": content_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if document_count is not None:
            collection_metadata["document_count"] = document_count
        if total_chars is not None:
            collection_metadata["total_chars"] = total_chars

        # Get or create collection
        collection = self.client.get_or_create_collection(
            name=collection_name, metadata=collection_metadata
        )

        # Generate IDs
        ids = [f"chunk_{i}" for i in range(len(chunks))]

        # Add metadata if not provided
        if metadatas is None:
            metadatas = [{"chunk_index": i} for i in range(len(chunks))]
        else:
            # Ensure chunk_index is in metadata
            for i, meta in enumerate(metadatas):
                if "chunk_index" not in meta:
                    meta["chunk_index"] = i

        # Store in ChromaDB
        collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

    def search_by_content(
        self, content_hash: str, query_embedding: List[float], top_k: int = 5
    ) -> List[SearchResult]:
        """Search for similar chunks using content hash and query embedding.

        Args:
            content_hash: SHA256 hash of document set
            query_embedding: Query embedding vector
            top_k: Number of results to return

        Returns:
            List of SearchResult objects, sorted by relevance

        Raises:
            ValueError: If collection doesn't exist for this content hash
        """
        collection_name = self.get_collection_name_by_content(content_hash)

        try:
            collection = self.client.get_collection(name=collection_name)
        except Exception:
            raise ValueError(
                f"No embeddings found for content hash {content_hash[:16]}... "
                "Generate embeddings first."
            )

        # Query ChromaDB
        results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

        # Parse results
        search_results = []
        if results["documents"] and len(results["documents"]) > 0:
            documents = results["documents"][0]
            distances = results["distances"][0]
            metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(documents)

            for doc, distance, metadata in zip(documents, distances, metadatas):
                # Convert distance to similarity score
                # ChromaDB returns L2 distance, convert to similarity
                score = 1.0 / (1.0 + distance)

                search_results.append(
                    SearchResult(
                        content=doc,
                        score=score,
                        metadata=metadata,
                        chunk_index=metadata.get("chunk_index", -1),
                    )
                )

        return search_results

    def cleanup_old_collections(self, days_to_keep: int = 10) -> int:
        """Delete collections older than specified days.

        Args:
            days_to_keep: Number of days to keep collections (default: 10)
                Collections created more than this many days ago will be deleted.

        Returns:
            Number of collections deleted
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        deleted_count = 0

        try:
            all_collections = self.client.list_collections()
        except Exception:
            return 0

        for collection in all_collections:
            # Only process RAG collections with our prefix
            if not collection.name.startswith(self.collection_prefix):
                continue

            # Check creation time from metadata
            created_at_str = collection.metadata.get("created_at")
            if not created_at_str:
                # No timestamp, skip
                continue

            try:
                created_at = datetime.fromisoformat(created_at_str)
                # Ensure timezone-aware comparison
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)

                if created_at < cutoff_time:
                    self.client.delete_collection(collection.name)
                    deleted_count += 1
                    print(
                        f"🗑️  Deleted old collection: {collection.name} (created {created_at.date()})"
                    )
            except (ValueError, Exception) as e:
                # Invalid timestamp format, skip
                print(f"⚠️  Could not parse timestamp for {collection.name}: {e}")
                continue

        return deleted_count
