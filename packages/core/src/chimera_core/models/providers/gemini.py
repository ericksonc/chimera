"""Google Gemini provider adapter.

Gemini's models.list() endpoint returns:
- Token limits (inputTokenLimit, outputTokenLimit)
- Supported generation methods
- But NO explicit multimodal capability flags

Multimodal support is inferred from model names.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from chimera_core.models.registry import (
    ModelCapabilities,
    ModelMetadata,
    Provider,
)

logger = logging.getLogger(__name__)

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiAdapter:
    """Adapter for fetching model metadata from Google Gemini API."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    @property
    def provider(self) -> Provider:
        return Provider.GEMINI

    def get_provider_name(self) -> str:
        return "Google Gemini"

    async def fetch_models(self) -> list[ModelMetadata]:
        """Fetch all models from Gemini API.

        Note: Requires API key. Rate limits depend on tier:
        - Free tier: 5-15 RPM
        - Tier 1: ~60 RPM
        - Tier 2: 1,000 RPM (after $250 cumulative spend)
        """
        if not self._api_key:
            logger.warning("Gemini API key not configured, skipping Gemini models")
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    GEMINI_MODELS_URL,
                    params={"key": self._api_key},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Gemini API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching Gemini models: {e}")
            raise

        models = []
        for model_data in data.get("models", []):
            try:
                metadata = self._parse_model(model_data)
                if metadata:
                    models.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to parse Gemini model {model_data.get('name')}: {e}")

        logger.info(f"Fetched {len(models)} models from Gemini")
        return models

    def _parse_model(self, data: dict[str, Any]) -> Optional[ModelMetadata]:
        """Parse Gemini model data into ModelMetadata."""
        # Gemini model names are like "models/gemini-1.5-pro"
        full_name = data.get("name", "")
        if not full_name:
            return None

        # Extract just the model name (remove "models/" prefix)
        model_id = full_name.replace("models/", "")

        # Skip embedding models
        if "embedding" in model_id.lower():
            return None

        # Parse capabilities
        capabilities = self._parse_capabilities(model_id, data)

        # Token limits
        input_limit = data.get("inputTokenLimit", 4096)
        output_limit = data.get("outputTokenLimit")

        return ModelMetadata(
            id=f"gemini:{model_id}",
            provider=Provider.GEMINI,
            provider_model_id=model_id,
            display_name=data.get("displayName", model_id),
            description=data.get("description"),
            capabilities=capabilities,
            pricing=None,  # Gemini API doesn't expose pricing
            max_context_window=input_limit,
            max_output_tokens=output_limit,
            is_available=True,
            last_updated=datetime.now(timezone.utc),
        )

    def _parse_capabilities(self, model_id: str, data: dict[str, Any]) -> ModelCapabilities:
        """Parse Gemini model capabilities.

        Since Gemini doesn't expose explicit capability flags, we infer from:
        1. Model name patterns
        2. supportedGenerationMethods array
        """
        methods = data.get("supportedGenerationMethods", [])
        model_lower = model_id.lower()

        # Vision models
        # Gemini 1.5 and 2.0 models support vision
        image_input = any(x in model_lower for x in ["1.5", "2.0", "2.5", "pro-vision", "flash"])

        # Audio input - Gemini 1.5+ and 2.0+ support audio
        audio_input = any(x in model_lower for x in ["1.5", "2.0", "2.5"])

        # Video input - Gemini 1.5+ supports video
        video_input = any(x in model_lower for x in ["1.5", "2.0", "2.5"])

        # Image output - Gemini 2.0 Flash can generate images
        image_output = "2.0-flash" in model_lower or "imagen" in model_lower

        # Function calling - most Gemini models support it
        function_calling = "generateContent" in methods

        # Streaming
        streaming = "streamGenerateContent" in methods

        return ModelCapabilities(
            text_input=True,
            image_input=image_input,
            audio_input=audio_input,
            video_input=video_input,
            text_output=True,
            image_output=image_output,
            audio_output=False,  # Not yet widely available
            function_calling=function_calling,
            streaming=streaming,
            json_mode=function_calling,
            system_prompt=True,
        )
