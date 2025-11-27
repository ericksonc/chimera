"""OpenRouter provider adapter.

OpenRouter provides the richest metadata of all providers:
- architecture.modality field for multimodal capabilities
- Complete pricing information
- Context window limits
- RSS feed for model updates (unique among providers)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from chimera_core.models.registry import (
    ModelCapabilities,
    ModelMetadata,
    ModelPricing,
    Provider,
)

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


class OpenRouterAdapter:
    """Adapter for fetching model metadata from OpenRouter."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")

    @property
    def provider(self) -> Provider:
        return Provider.OPENROUTER

    def get_provider_name(self) -> str:
        return "OpenRouter"

    async def fetch_models(self) -> list[ModelMetadata]:
        """Fetch all models from OpenRouter API.

        Returns comprehensive metadata including:
        - Model ID and display name
        - Modality (text, image, audio capabilities)
        - Pricing per token type
        - Context window and output limits
        """
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(OPENROUTER_MODELS_URL, headers=headers, timeout=30.0)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"OpenRouter API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching OpenRouter models: {e}")
            raise

        models = []
        for model_data in data.get("data", []):
            try:
                metadata = self._parse_model(model_data)
                if metadata:
                    models.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to parse OpenRouter model {model_data.get('id')}: {e}")

        logger.info(f"Fetched {len(models)} models from OpenRouter")
        return models

    def _parse_model(self, data: dict[str, Any]) -> Optional[ModelMetadata]:
        """Parse OpenRouter model data into ModelMetadata."""
        model_id = data.get("id")
        if not model_id:
            return None

        # Parse capabilities from architecture.modality
        capabilities = self._parse_capabilities(data)

        # Parse pricing
        pricing = self._parse_pricing(data)

        # Context window
        context_length = data.get("context_length", 4096)
        max_output = data.get("top_provider", {}).get("max_completion_tokens")

        return ModelMetadata(
            id=f"openrouter:{model_id}",
            provider=Provider.OPENROUTER,
            provider_model_id=model_id,
            display_name=data.get("name", model_id),
            description=data.get("description"),
            capabilities=capabilities,
            pricing=pricing,
            max_context_window=context_length,
            max_output_tokens=max_output,
            is_available=True,
            last_updated=datetime.now(timezone.utc),
        )

    def _parse_capabilities(self, data: dict[str, Any]) -> ModelCapabilities:
        """Parse OpenRouter modality into capability flags.

        OpenRouter uses architecture.modality format like:
        - "text->text" (text only)
        - "text+image->text" (vision)
        - "text+image+audio->text" (multimodal input)
        - "text->text+image" (image generation)
        """
        modality = data.get("architecture", {}).get("modality", "text->text")

        # Parse input modalities (before ->)
        input_part, output_part = "text", "text"
        if "->" in modality:
            parts = modality.split("->")
            input_part = parts[0] if len(parts) > 0 else "text"
            output_part = parts[1] if len(parts) > 1 else "text"

        # Determine input capabilities
        image_input = "image" in input_part
        audio_input = "audio" in input_part
        video_input = "video" in input_part

        # Determine output capabilities
        image_output = "image" in output_part
        audio_output = "audio" in output_part

        # Function calling - check if model supports it
        # OpenRouter doesn't expose this directly, infer from model family
        function_calling = self._infer_function_calling(data.get("id", ""))

        return ModelCapabilities(
            text_input=True,
            image_input=image_input,
            audio_input=audio_input,
            video_input=video_input,
            text_output=True,
            image_output=image_output,
            audio_output=audio_output,
            function_calling=function_calling,
            streaming=True,
            json_mode=function_calling,  # Usually correlates
            system_prompt=True,
        )

    def _infer_function_calling(self, model_id: str) -> bool:
        """Infer function calling support from model ID.

        Most modern models support function calling. This is a heuristic
        until OpenRouter exposes this directly.
        """
        # Known function-calling models/families
        fc_patterns = [
            "claude",
            "gpt-4",
            "gpt-3.5",
            "gemini",
            "mistral",
            "mixtral",
            "llama-3",
            "qwen",
            "command",
            "deepseek",
        ]
        model_lower = model_id.lower()
        return any(pattern in model_lower for pattern in fc_patterns)

    def _parse_pricing(self, data: dict[str, Any]) -> Optional[ModelPricing]:
        """Parse OpenRouter pricing into ModelPricing.

        OpenRouter provides pricing per token, we convert to per million.
        """
        pricing = data.get("pricing", {})
        if not pricing:
            return None

        # OpenRouter uses string values like "0.00001"
        try:
            prompt_price = float(pricing.get("prompt", 0))
            completion_price = float(pricing.get("completion", 0))

            # Convert per-token to per-million
            return ModelPricing(
                input_cost_per_million=prompt_price * 1_000_000,
                output_cost_per_million=completion_price * 1_000_000,
                image_cost_per_image=float(pricing.get("image", 0))
                if pricing.get("image")
                else None,
            )
        except (ValueError, TypeError):
            return None
