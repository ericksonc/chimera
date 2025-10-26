"""Model factory for creating Pydantic AI models from different providers.

This module provides a factory function that creates the appropriate Pydantic AI
model based on the model string. Currently supports:
- Gemini models (strings starting with "gemini-")
- DeepInfra models via OpenAI-compatible API (everything else)
"""

import os
from typing import Union, Optional
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.models.openai import OpenAIModel


def create_model(model_name: str) -> Union[GeminiModel, OpenAIModel]:
    """Create a Pydantic AI model based on the model name string.
    
    Detection logic:
    - If model_name starts with "gemini-" -> create GeminiModel
    - Otherwise -> create OpenAIModel for DeepInfra
    
    Args:
        model_name: Model identifier string (e.g., "gemini-2.5-flash" or "Qwen/Qwen2.5-72B-Instruct")
        
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
        # DeepInfra model via OpenAI-compatible endpoint
        api_key = os.getenv("DEEPINFRA_KEY") or os.getenv("DEEPINFRA_TOKEN")
        if not api_key:
            raise ValueError(
                "DeepInfra API key not found. Set DEEPINFRA_KEY or DEEPINFRA_TOKEN environment variable."
            )
        # Set environment variables for OpenAI client to use DeepInfra
        # OpenAIModel will pick these up automatically
        os.environ['OPENAI_API_KEY'] = api_key
        os.environ['OPENAI_BASE_URL'] = "https://api.deepinfra.com/v1/openai"
        
        return OpenAIModel(model_name)