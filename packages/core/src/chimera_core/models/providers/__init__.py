"""Provider adapters for model metadata fetching.

Each adapter implements the ProviderAdapter protocol to fetch model
metadata from a specific provider's API.
"""

from .base import ProviderAdapter
from .gemini import GeminiAdapter
from .kimi import KimiAdapter
from .openrouter import OpenRouterAdapter

__all__ = ["ProviderAdapter", "OpenRouterAdapter", "GeminiAdapter", "KimiAdapter"]
