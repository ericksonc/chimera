"""Voyage AI embedding service for RAG.

This module provides embedding generation using Voyage AI's voyage-3-large model.
"""

import os
from dataclasses import dataclass
from typing import List, Optional

import httpx


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""

    embeddings: List[List[float]]
    model: str
    total_tokens: int


class VoyageEmbeddingService:
    """Service for generating embeddings via Voyage AI API.

    Uses voyage-3-large model for high-quality embeddings.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "voyage-3-large",
        base_url: str = "https://api.voyageai.com/v1",
    ):
        """Initialize Voyage AI embedding service.

        Args:
            api_key: Voyage AI API key (defaults to VOYAGE_API_KEY env var)
            model: Model to use for embeddings
            base_url: API base URL
        """
        self.api_key = api_key or os.getenv("VOYAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Voyage API key not found. Set VOYAGE_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.model = model
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )

    async def embed_texts(self, texts: List[str], input_type: str = "document") -> EmbeddingResult:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            input_type: Type of input ("document" or "query")
                - "document": For indexing documents
                - "query": For search queries

        Returns:
            EmbeddingResult with embeddings and metadata

        Raises:
            httpx.HTTPError: If API request fails
        """
        if not texts:
            raise ValueError("Cannot embed empty text list")

        # Voyage AI API endpoint
        url = f"{self.base_url}/embeddings"

        payload = {"input": texts, "model": self.model, "input_type": input_type}

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract embeddings in order
            embeddings = [item["embedding"] for item in data["data"]]

            return EmbeddingResult(
                embeddings=embeddings,
                model=data["model"],
                total_tokens=data["usage"]["total_tokens"],
            )

        except httpx.HTTPStatusError as e:
            # Try to get error details from response body
            try:
                error_detail = e.response.json()
                error_msg = error_detail.get("detail", error_detail)
            except Exception:
                error_msg = e.response.text
            raise RuntimeError(
                f"Voyage AI API error: {e.response.status_code} - {error_msg}"
            ) from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to generate embeddings: {e}") from e

    async def embed_single(self, text: str, input_type: str = "document") -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed
            input_type: Type of input ("document" or "query")

        Returns:
            Embedding vector as list of floats
        """
        result = await self.embed_texts([text], input_type=input_type)
        return result.embeddings[0]

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
