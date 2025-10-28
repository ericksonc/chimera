"""ThreadProtocolTransformer Protocol - Convert events to ModelMessages.

This protocol defines the interface for transforming ThreadProtocol JSONL events
into Pydantic AI ModelMessage objects for agent execution.
"""

from __future__ import annotations
from typing import Protocol, runtime_checkable, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage


@runtime_checkable
class ThreadProtocolTransformer(Protocol):
    """Transforms ThreadProtocol events to ModelMessages."""

    def transform(
        self,
        events: list[dict],
        agent_id: UUID | None = None
    ) -> list[ModelMessage]:
        """Transform ThreadProtocol events to ModelMessages.

        Args:
            events: List of ThreadProtocol events (Lines 2+ of JSONL)
            agent_id: If specified, filter to only this agent's perspective

        Returns:
            List of ModelMessage objects for Pydantic AI

        Note:
            This is the interface for both generic and opinionated transformers.
            - GenericTransformer: Minimal transformation, nearly verbatim
            - OpinionatedTransformer: Space-specific formatting and filtering
        """
        ...
