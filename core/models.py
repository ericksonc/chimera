"""Model factory for creating Pydantic AI models from different providers.

This module provides a factory function that creates the appropriate Pydantic AI
model based on the model string. Currently supports:
- Gemini models (strings starting with "gemini-")
- OpenRouter models (everything else)
"""

import os
from typing import Union
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider


def create_model(model_name: str) -> Union[GeminiModel, OpenAIChatModel]:
    """Create a Pydantic AI model based on the model name string.

    Detection logic:
    - If model_name starts with "gemini-" -> create GeminiModel
    - Otherwise -> create OpenAIChatModel with OpenRouterProvider

    Args:
        model_name: Model identifier string (e.g., "gemini-2.5-flash" or "anthropic/claude-3.5-sonnet")

    Returns:
        Configured Pydantic AI model instance

    Raises:
        ValueError: If API keys are missing for the selected provider
    """
    if model_name.startswith("gemini-"):
        # Gemini model
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "Gemini API key not found. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
            )
        # Ensure GEMINI_API_KEY is set for the GeminiModel to use
        if not os.getenv("GEMINI_API_KEY"):
            os.environ['GEMINI_API_KEY'] = api_key
        return GeminiModel(model_name)
    else:
        # OpenRouter model
        api_key = os.getenv("OPENROUTER_KEY")
        if not api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_KEY environment variable."
            )

        return OpenAIChatModel(
            model_name,
            provider=OpenRouterProvider(api_key=api_key)
        )