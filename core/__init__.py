"""Chimera core - Main execution and protocol implementations."""

# Core types
from core.widget import Widget, StatefulWidget
from core.agent import Agent
from core.spaces.generic_space import GenericSpace
from core.thread import ThreadState

# Protocols
from core.protocols.readable_thread_state import (
    ActiveSpace,
    ActiveAgent,
    ReadableThreadState,
)

# ThreadProtocol
from core.threadprotocol.writer import ThreadProtocolWriter
from core.threadprotocol.reader import ThreadProtocolReader
from core.threadprotocol.blueprint import (
    Blueprint,
    InlineAgentConfig,
    ReferencedAgentConfig,
    DefaultSpaceConfig,
    ReferencedSpaceConfig,
    ComponentConfig,
    create_simple_blueprint,
)
from core.threadprotocol.transformer import GenericTransformer

__all__ = [
    # Core types
    'Widget',
    'StatefulWidget',
    'Agent',
    'GenericSpace',
    'ThreadState',
    # Protocols
    'ActiveSpace',
    'ActiveAgent',
    'ReadableThreadState',
    # ThreadProtocol
    'ThreadProtocolWriter',
    'ThreadProtocolReader',
    'Blueprint',
    'InlineAgentConfig',
    'ReferencedAgentConfig',
    'DefaultSpaceConfig',
    'ReferencedSpaceConfig',
    'ComponentConfig',
    'create_simple_blueprint',
    'GenericTransformer',
]