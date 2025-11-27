"""Model Registry Service.

Central service for aggregating, caching, and querying model metadata
from multiple providers. Features:
- Multi-provider aggregation (OpenRouter, Gemini, Kimi)
- Redis caching with TTL (graceful fallback to in-memory)
- LiteLLM enrichment for capabilities/pricing
- Background polling for model list updates
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from chimera_core.cache import CacheClient, get_cache_client
from chimera_core.models.providers import (
    GeminiAdapter,
    KimiAdapter,
    OpenRouterAdapter,
    ProviderAdapter,
)
from chimera_core.models.registry import (
    ModelMetadata,
    ModelPricing,
    Provider,
)

logger = logging.getLogger(__name__)

# Cache keys
CACHE_KEY_ALL_MODELS = "models:all"
CACHE_KEY_PROVIDER = "models:provider:{provider}"
CACHE_KEY_MODEL = "models:meta:{model_id}"

# Default TTL in seconds
DEFAULT_CACHE_TTL = int(os.getenv("MODEL_REGISTRY_CACHE_TTL", "300"))  # 5 minutes


class ModelRegistryService:
    """Central service for model metadata management.

    Aggregates models from multiple providers, caches results,
    and provides query methods for model discovery and validation.
    """

    def __init__(
        self,
        cache_client: Optional[CacheClient] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
    ):
        self._cache = cache_client or get_cache_client()
        self._cache_ttl = cache_ttl
        self._adapters: list[ProviderAdapter] = [
            OpenRouterAdapter(),
            GeminiAdapter(),
            KimiAdapter(),
        ]
        self._local_cache: dict[str, ModelMetadata] = {}  # Fast lookup cache
        self._last_refresh: Optional[datetime] = None

    async def get_all_models(self, force_refresh: bool = False) -> list[ModelMetadata]:
        """Get all available models from all providers.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data.

        Returns:
            List of all available models across all providers.
        """
        if not force_refresh:
            # Try cache first
            cached = await self._cache.get_json(CACHE_KEY_ALL_MODELS)
            if cached:
                models = [ModelMetadata(**m) for m in cached]
                self._update_local_cache(models)
                return models

        # Fetch from all providers
        models = await self._fetch_all_providers()

        # Cache results
        await self._cache.set_json(
            CACHE_KEY_ALL_MODELS,
            [m.model_dump(mode="json") for m in models],
            ttl=self._cache_ttl,
        )

        self._update_local_cache(models)
        self._last_refresh = datetime.now(timezone.utc)

        return models

    async def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """Get metadata for a specific model.

        Args:
            model_id: Model ID (can be full ID like "openrouter:anthropic/claude-3.5-sonnet"
                     or just provider model ID like "anthropic/claude-3.5-sonnet")

        Returns:
            ModelMetadata if found, None otherwise.
        """
        # Check local cache first
        if model_id in self._local_cache:
            return self._local_cache[model_id]

        # Check for provider_model_id match
        for cached_model in self._local_cache.values():
            if cached_model.provider_model_id == model_id:
                return cached_model

        # Try individual model cache
        cached = await self._cache.get_json(CACHE_KEY_MODEL.format(model_id=model_id))
        if cached:
            return ModelMetadata(**cached)

        # Fall back to full fetch
        all_models = await self.get_all_models()
        for model in all_models:
            if model.id == model_id or model.provider_model_id == model_id:
                return model

        return None

    async def get_models_by_provider(self, provider: Provider) -> list[ModelMetadata]:
        """Get all models from a specific provider.

        Args:
            provider: Provider enum value.

        Returns:
            List of models from the specified provider.
        """
        all_models = await self.get_all_models()
        return [m for m in all_models if m.provider == provider]

    async def get_models_by_capability(self, capability: str) -> list[ModelMetadata]:
        """Get all models that support a specific capability.

        Args:
            capability: Capability name (e.g., 'image_input', 'function_calling')

        Returns:
            List of models supporting the capability.
        """
        all_models = await self.get_all_models()
        return [m for m in all_models if m.supports(capability)]

    async def validate_model(self, model_id: str) -> bool:
        """Check if a model ID is valid and available.

        Args:
            model_id: Model ID to validate.

        Returns:
            True if model exists and is available, False otherwise.
        """
        model = await self.get_model(model_id)
        return model is not None and model.is_available

    def supports_capability(self, model_id: str, capability: str) -> bool:
        """Check if a model supports a capability (sync, from local cache).

        Args:
            model_id: Model ID.
            capability: Capability name.

        Returns:
            True if model supports capability, False if not or unknown.
        """
        model = self._local_cache.get(model_id)
        if model:
            return model.supports(capability)

        # Check by provider_model_id
        for cached_model in self._local_cache.values():
            if cached_model.provider_model_id == model_id:
                return cached_model.supports(capability)

        return False

    async def refresh_cache(self) -> int:
        """Force refresh all model caches.

        Returns:
            Number of models fetched.
        """
        models = await self.get_all_models(force_refresh=True)
        return len(models)

    async def _fetch_all_providers(self) -> list[ModelMetadata]:
        """Fetch models from all providers concurrently."""
        tasks = [self._fetch_provider(adapter) for adapter in self._adapters]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_models: list[ModelMetadata] = []
        for result, adapter in zip(results, self._adapters):
            if isinstance(result, BaseException):
                logger.error(f"Failed to fetch from {adapter.get_provider_name()}: {result}")
            elif isinstance(result, list):
                all_models.extend(result)

        # Enrich with LiteLLM if available
        all_models = await self._enrich_with_litellm(all_models)

        return all_models

    async def _fetch_provider(self, adapter: ProviderAdapter) -> list[ModelMetadata]:
        """Fetch models from a single provider."""
        try:
            models = await adapter.fetch_models()
            logger.info(f"Fetched {len(models)} models from {adapter.get_provider_name()}")
            return models  # type: ignore[no-any-return]  # Protocol return type
        except Exception as e:
            logger.error(f"Provider {adapter.get_provider_name()} fetch failed: {e}")
            return []

    async def _enrich_with_litellm(self, models: list[ModelMetadata]) -> list[ModelMetadata]:
        """Enrich model metadata with LiteLLM registry data.

        LiteLLM maintains a comprehensive registry of model capabilities and pricing.
        We use it as a secondary source to fill in missing information.
        """
        try:
            from litellm import model_cost  # type: ignore[import-not-found]
        except ImportError:
            logger.debug("LiteLLM not installed, skipping enrichment")
            return models

        enriched = []
        for model in models:
            # Try to find model in LiteLLM registry
            litellm_key = self._get_litellm_key(model)
            litellm_data = model_cost.get(litellm_key) if litellm_key else None

            if litellm_data:
                model = self._apply_litellm_enrichment(model, litellm_data)

            enriched.append(model)

        return enriched

    def _get_litellm_key(self, model: ModelMetadata) -> Optional[str]:
        """Convert model ID to LiteLLM registry key format."""
        # LiteLLM uses various key formats depending on provider
        # Try common patterns
        provider_model = model.provider_model_id

        if model.provider == Provider.OPENROUTER:
            # OpenRouter models might be indexed by provider/model format
            return provider_model
        elif model.provider == Provider.GEMINI:
            # Gemini models use gemini-* format
            return provider_model
        elif model.provider == Provider.KIMI:
            # Kimi models might be under moonshot-*
            return provider_model

        return None

    def _apply_litellm_enrichment(self, model: ModelMetadata, litellm_data: dict) -> ModelMetadata:
        """Apply LiteLLM data to enhance model metadata."""
        # Update pricing if not already set
        if model.pricing is None and (
            litellm_data.get("input_cost_per_token") or litellm_data.get("output_cost_per_token")
        ):
            input_cost = litellm_data.get("input_cost_per_token", 0) * 1_000_000
            output_cost = litellm_data.get("output_cost_per_token", 0) * 1_000_000
            model = model.model_copy(
                update={
                    "pricing": ModelPricing(
                        input_cost_per_million=input_cost,
                        output_cost_per_million=output_cost,
                    )
                }
            )

        # Update capabilities from LiteLLM
        caps_updates = {}
        if litellm_data.get("supports_vision") and not model.capabilities.image_input:
            caps_updates["image_input"] = True
        if (
            litellm_data.get("supports_function_calling")
            and not model.capabilities.function_calling
        ):
            caps_updates["function_calling"] = True

        if caps_updates:
            new_caps = model.capabilities.model_copy(update=caps_updates)
            model = model.model_copy(update={"capabilities": new_caps})

        # Update context window if LiteLLM has better info
        litellm_context = litellm_data.get("max_tokens") or litellm_data.get("max_input_tokens")
        if litellm_context and litellm_context > model.max_context_window:
            model = model.model_copy(update={"max_context_window": litellm_context})

        return model

    def _update_local_cache(self, models: list[ModelMetadata]) -> None:
        """Update local cache with fetched models.

        Only indexes by model.id to avoid collision when multiple providers
        expose the same provider_model_id. Lookups by provider_model_id
        iterate over values (see get_model, supports_capability).
        """
        self._local_cache.clear()
        for model in models:
            self._local_cache[model.id] = model


# Global service instance
_registry_service: Optional[ModelRegistryService] = None


def get_registry_service() -> ModelRegistryService:
    """Get or create the global model registry service."""
    global _registry_service
    if _registry_service is None:
        _registry_service = ModelRegistryService()
    return _registry_service


async def initialize_registry() -> int:
    """Initialize the registry by fetching initial model data.

    Call this during application startup to warm the cache.

    Returns:
        Number of models loaded.
    """
    service = get_registry_service()
    return await service.refresh_cache()
