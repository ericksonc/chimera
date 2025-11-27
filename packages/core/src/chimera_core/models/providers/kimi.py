"""Kimi (Moonshot AI) provider adapter.

Kimi/Moonshot AI has NO model listing endpoint.
Model metadata must be extracted from static documentation at platform.moonshot.ai/docs.

This adapter provides hardcoded model definitions that should be updated
manually when new models are released.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from chimera_core.models.registry import (
    ModelCapabilities,
    ModelMetadata,
    ModelPricing,
    Provider,
)

logger = logging.getLogger(__name__)

# Static Kimi model definitions
# Last updated: 2025-11
# Source: https://platform.moonshot.ai/docs
KIMI_MODELS = [
    {
        "id": "kimi-k2-0905",
        "display_name": "Kimi K2",
        "description": "Moonshot AI's flagship model with strong reasoning capabilities",
        "context_window": 131072,  # 128K
        "max_output": 8192,
        "capabilities": {
            "image_input": True,
            "function_calling": True,
        },
        "pricing": {
            "input": 1.0,  # per million tokens
            "output": 3.0,
        },
    },
    {
        "id": "moonshot-v1-8k",
        "display_name": "Moonshot V1 8K",
        "description": "Fast model optimized for shorter contexts",
        "context_window": 8192,
        "max_output": 4096,
        "capabilities": {
            "image_input": False,
            "function_calling": True,
        },
        "pricing": {
            "input": 0.5,
            "output": 1.5,
        },
    },
    {
        "id": "moonshot-v1-32k",
        "display_name": "Moonshot V1 32K",
        "description": "Balanced model for medium-length contexts",
        "context_window": 32768,
        "max_output": 8192,
        "capabilities": {
            "image_input": False,
            "function_calling": True,
        },
        "pricing": {
            "input": 0.8,
            "output": 2.0,
        },
    },
    {
        "id": "moonshot-v1-128k",
        "display_name": "Moonshot V1 128K",
        "description": "Long-context model for extensive documents",
        "context_window": 131072,
        "max_output": 8192,
        "capabilities": {
            "image_input": False,
            "function_calling": True,
        },
        "pricing": {
            "input": 1.0,
            "output": 3.0,
        },
    },
]


class KimiAdapter:
    """Adapter for Kimi/Moonshot AI models.

    Since Moonshot doesn't provide a model listing API, this adapter
    returns static model definitions that should be updated manually.
    """

    def __init__(self, api_key: Optional[str] = None):
        # API key not needed for static definitions
        # but stored for potential future API integration
        self._api_key = api_key

    @property
    def provider(self) -> Provider:
        return Provider.KIMI

    def get_provider_name(self) -> str:
        return "Kimi (Moonshot AI)"

    async def fetch_models(self) -> list[ModelMetadata]:
        """Return static model definitions.

        Note: These are hardcoded since Moonshot doesn't provide a models API.
        Update KIMI_MODELS when new models are released.
        """
        models = []
        for model_data in KIMI_MODELS:
            try:
                metadata = self._parse_model(model_data)
                if metadata:
                    models.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to parse Kimi model {model_data.get('id')}: {e}")

        logger.info(f"Loaded {len(models)} static Kimi model definitions")
        return models

    def _parse_model(self, data: dict) -> Optional[ModelMetadata]:
        """Parse static model definition into ModelMetadata."""
        model_id = data.get("id")
        if not model_id:
            return None

        caps_data = data.get("capabilities", {})
        capabilities = ModelCapabilities(
            text_input=True,
            image_input=caps_data.get("image_input", False),
            audio_input=caps_data.get("audio_input", False),
            video_input=caps_data.get("video_input", False),
            text_output=True,
            image_output=False,
            audio_output=False,
            function_calling=caps_data.get("function_calling", False),
            streaming=True,
            json_mode=caps_data.get("function_calling", False),
            system_prompt=True,
        )

        pricing_data = data.get("pricing")
        pricing = None
        if pricing_data:
            pricing = ModelPricing(
                input_cost_per_million=pricing_data.get("input", 0),
                output_cost_per_million=pricing_data.get("output", 0),
            )

        return ModelMetadata(
            id=f"kimi:{model_id}",
            provider=Provider.KIMI,
            provider_model_id=model_id,
            display_name=data.get("display_name", model_id),
            description=data.get("description"),
            capabilities=capabilities,
            pricing=pricing,
            max_context_window=data.get("context_window", 8192),
            max_output_tokens=data.get("max_output"),
            is_available=True,
            last_updated=datetime.now(timezone.utc),
        )
