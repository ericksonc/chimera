"""Model factory for creating Pydantic AI models from different providers.

This module provides a factory function that creates the appropriate Pydantic AI
model based on the model string. Currently supports:
- Gemini models (strings starting with "gemini-")
- Kimi K2 models via official Moonshot API (strings starting with "kimi-k2")
- OpenRouter models (everything else)

The factory can optionally integrate with ModelRegistryService for validation,
logging warnings for unrecognized models while still attempting creation.
"""

import logging
import os
from typing import Union

from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.moonshotai import MoonshotAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)


def create_model(model_name: str, validate: bool = False) -> Union[GeminiModel, OpenAIChatModel]:
    """Create a Pydantic AI model based on the model name string.

    Detection logic:
    - If model_name starts with "gemini-" -> create GeminiModel
    - If model_name starts with "kimi-k2" -> create OpenAIChatModel with MoonshotAIProvider
    - Otherwise -> create OpenAIChatModel with OpenRouterProvider

    Args:
        model_name: Model identifier string (e.g., "gemini-2.5-flash", "kimi-k2-0905", or "anthropic/claude-3.5-sonnet")
        validate: If True, check model against registry and log warning if not found.
                  Model creation still proceeds even if validation fails.

    Returns:
        Configured Pydantic AI model instance

    Raises:
        ValueError: If API keys are missing for the selected provider
    """
    # Optional registry validation
    if validate:
        _validate_model_name(model_name)
    if model_name.startswith("gemini-"):
        # Gemini model
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "Gemini API key not found. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
            )
        # Ensure GEMINI_API_KEY is set for the GeminiModel to use
        if not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = api_key
        return GeminiModel(model_name)
    elif model_name.startswith("kimi-k2"):
        # Kimi K2 via official Moonshot API
        api_key = os.getenv("MOONSHOTAI_API_KEY")
        if not api_key:
            raise ValueError(
                "Moonshot API key not found. Set MOONSHOTAI_API_KEY environment variable."
            )

        return OpenAIChatModel(model_name, provider=MoonshotAIProvider(api_key=api_key))
    else:
        # OpenRouter model
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable."
            )

        return OpenAIChatModel(model_name, provider=OpenRouterProvider(api_key=api_key))


def _validate_model_name(model_name: str) -> None:
    """Validate model name against registry (sync check from local cache).

    Logs a warning if the model is not found in the registry.
    Does not block model creation - just informational.
    """
    try:
        from .registry_service import get_registry_service

        service = get_registry_service()
        # Use sync local cache check
        if model_name not in service._local_cache:
            # Also check by provider_model_id
            found = any(m.provider_model_id == model_name for m in service._local_cache.values())
            if not found:
                logger.warning(
                    f"Model '{model_name}' not found in registry. "
                    "Proceeding with creation anyway. "
                    "Run initialize_registry() to populate the cache."
                )
    except ImportError:
        # Registry not available, skip validation
        pass
    except Exception as e:
        logger.debug(f"Registry validation skipped: {e}")
