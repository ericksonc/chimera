"""Widget Registry - Maps class names to Widget classes for hydration.

This module provides a registry pattern for looking up Widget classes by their
fully-qualified class name (e.g., "chimera.widgets.QAWidget") and instantiating
them from ComponentConfig during Blueprint hydration.
"""

from typing import TYPE_CHECKING, Dict, Type

from .threadprotocol.blueprint import ComponentConfig
from .widget import Widget

if TYPE_CHECKING:
    from chimera_core.agent import Agent

# Global widget registry
_WIDGET_REGISTRY: Dict[str, Type[Widget]] = {}


def register_widget(class_name: str, widget_class: Type[Widget]) -> None:
    """Register a widget class for hydration.

    Args:
        class_name: Fully-qualified class name (e.g., "chimera.widgets.QAWidget")
        widget_class: The Widget class to register
    """
    _WIDGET_REGISTRY[class_name] = widget_class


def hydrate_widget(config: ComponentConfig, agent: "Agent") -> Widget:
    """Hydrate a Widget instance from ComponentConfig.

    Looks up the widget class by name and calls its from_blueprint_config() method.

    Args:
        config: ComponentConfig from Blueprint
        agent: Agent instance that owns this widget (provides context like identifier)

    Returns:
        Instantiated Widget

    Raises:
        KeyError: If widget class is not registered
        ValueError: If config is invalid
    """
    widget_class = _WIDGET_REGISTRY.get(config.class_name)

    if widget_class is None:
        raise KeyError(
            f"Widget class '{config.class_name}' is not registered. "
            f"Did you forget to call register_widget()? "
            f"Available widgets: {list(_WIDGET_REGISTRY.keys())}"
        )

    return widget_class.from_blueprint_config(config, agent)


def get_registered_widgets() -> Dict[str, Type[Widget]]:
    """Get all registered widget classes.

    Returns:
        Dictionary mapping class names to Widget classes
    """
    return _WIDGET_REGISTRY.copy()


# Auto-import built-in widgets to trigger metaclass registration
def _import_builtin_widgets():
    """Import all built-in widgets to trigger PluginMeta auto-registration.

    The PluginMeta metaclass automatically registers widgets when they're
    defined, so we just need to ensure they're imported. No manual
    register_widget() calls needed.
    """

    # Widgets are auto-registered via PluginMeta metaclass
    # We just need to import the module to trigger it
    import chimera_core.widgets  # noqa: F401


# Import widgets on module load to trigger auto-registration
_import_builtin_widgets()
