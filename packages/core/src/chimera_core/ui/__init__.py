"""UI adapter infrastructure for transforming internal events to UI protocols.

This module provides the base classes and utilities for converting ThreadProtocol
events to various UI streaming protocols (Vercel AI SDK, AG-UI, etc.).
"""

# Import VSP event types for type hints and validation
from . import vsp_events
from .event_stream import UIEventStream
from .streaming_infrastructure import StreamingInfrastructure, create_streaming_infrastructure
from .threadprotocol_persistence import (
    ThreadProtocolPersistenceWrapper,
    emit_tool_approval_request,
    emit_tool_output_denied,
)
from .utils import CamelBaseModel, to_camel
from .vsp_event_stream import VSPEventStream

__all__ = [
    "CamelBaseModel",
    "to_camel",
    "UIEventStream",
    "VSPEventStream",
    "ThreadProtocolPersistenceWrapper",
    "emit_tool_output_denied",
    "emit_tool_approval_request",
    "vsp_events",
    "StreamingInfrastructure",
    "create_streaming_infrastructure",
]
