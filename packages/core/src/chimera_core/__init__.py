"""Chimera core - Main execution and protocol implementations."""

# Core types
from chimera_core.agent import Agent

# Protocols
from chimera_core.protocols.readable_thread_state import (
    ActiveAgent,
    ActiveSpace,
    ReadableThreadState,
)
from chimera_core.spaces.generic_space import GenericSpace
from chimera_core.thread import ThreadState

# from chimera_core.threadprotocol.reader import ThreadProtocolReader TODO: I think it's dead code, remove
from chimera_core.threadprotocol.blueprint import (
    Blueprint,
    ComponentConfig,
    DefaultSpaceConfig,
    InlineAgentConfig,
    ReferencedAgentConfig,
    ReferencedSpaceConfig,
    create_simple_blueprint,
)
from chimera_core.threadprotocol.transformer import GenericTransformer

# ThreadProtocol
from chimera_core.threadprotocol.writer import ThreadProtocolWriter
from chimera_core.widget import StatefulWidget, Widget

__all__ = [
    # Core types
    "Widget",
    "StatefulWidget",
    "Agent",
    "GenericSpace",
    "ThreadState",
    # Protocols
    "ActiveSpace",
    "ActiveAgent",
    "ReadableThreadState",
    # ThreadProtocol
    "ThreadProtocolWriter",
    "ThreadProtocolReader",
    "Blueprint",
    "InlineAgentConfig",
    "ReferencedAgentConfig",
    "DefaultSpaceConfig",
    "ReferencedSpaceConfig",
    "ComponentConfig",
    "create_simple_blueprint",
    "GenericTransformer",
]
