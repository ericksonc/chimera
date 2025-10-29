"""Chimera core - Main execution and protocol implementations."""

# Re-export key classes for convenience
from core.base import (
    Widget,
    Space,
    GenericSpace,
    Agent,
    Blueprint,
    ThreadState
)

from core.threadprotocol.writer import ThreadProtocolWriter
from core.threadprotocol.reader import ThreadProtocolReader
from core.threadprotocol.blueprint import (
    Blueprint as BlueprintConfig,
    InlineAgentConfig,
    ReferencedAgentConfig,
    DefaultSpaceConfig,
    ReferencedSpaceConfig,
    WidgetConfig,
    create_simple_blueprint,
)
from core.threadprotocol.transformer import GenericTransformer

__all__ = [
    # Base types
    'Widget',
    'Space',
    'GenericSpace',
    'Agent',
    'Blueprint',
    'ThreadState',
    # ThreadProtocol
    'ThreadProtocolWriter',
    'ThreadProtocolReader',
    'BlueprintConfig',
    'InlineAgentConfig',
    'ReferencedAgentConfig',
    'DefaultSpaceConfig',
    'ReferencedSpaceConfig',
    'WidgetConfig',
    'create_simple_blueprint',
    'GenericTransformer',
]