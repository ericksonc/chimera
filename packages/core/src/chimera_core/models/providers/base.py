"""Base protocol for provider adapters."""

from typing import Protocol, runtime_checkable

from chimera_core.models.registry import ModelMetadata, Provider


@runtime_checkable
class ProviderAdapter(Protocol):
    """Protocol for provider adapters.

    Each provider adapter is responsible for:
    1. Fetching available models from the provider's API
    2. Transforming provider-specific responses to ModelMetadata
    3. Handling authentication and rate limiting
    """

    @property
    def provider(self) -> Provider:
        """Return the provider enum value."""
        ...

    async def fetch_models(self) -> list[ModelMetadata]:
        """Fetch all available models from this provider.

        Returns:
            List of ModelMetadata objects for all available models.

        Raises:
            Exception: If API call fails (caller should handle gracefully).
        """
        ...

    def get_provider_name(self) -> str:
        """Return human-readable provider name."""
        ...
