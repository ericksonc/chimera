"""Model factory, registry, and adapters for Pydantic AI models."""

from .factory import create_model
from .kimi import KimiChatModel
from .registry import (
    ModelCapabilities,
    ModelMetadata,
    ModelPricing,
    Provider,
)
from .registry_service import (
    ModelRegistryService,
    get_registry_service,
    initialize_registry,
)

__all__ = [
    "create_model",
    "KimiChatModel",
    # Registry types
    "ModelCapabilities",
    "ModelMetadata",
    "ModelPricing",
    "Provider",
    # Registry service
    "ModelRegistryService",
    "get_registry_service",
    "initialize_registry",
]
