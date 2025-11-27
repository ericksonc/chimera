"""ThreadProtocolTransformer Protocol - Convert events to ModelMessages.

This protocol defines the interface for transforming ThreadProtocol JSONL events
into Pydantic AI ModelMessage objects for agent execution, and building
DeferredToolResults for resuming agent runs after tool approvals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.tools import DeferredToolResults

    from chimera_core.types.user_input import UserInput


@runtime_checkable
class ThreadProtocolTransformer(Protocol):
    """Transforms ThreadProtocol events to ModelMessages and DeferredToolResults."""

    def transform(self, events: list[dict], agent_id: UUID | None = None) -> list[ModelMessage]:
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

    def build_deferred_tool_results(
        self, events: list[dict], user_input: "UserInput | None" = None
    ) -> "DeferredToolResults | None":
        """Build DeferredToolResults from user approval/denial data.

        This method converts user input containing tool approvals or external
        tool results into a DeferredToolResults object that PAI can use to
        resume an agent run that was paused for tool approval.

        Args:
            events: List of ThreadProtocol events (for context if needed)
            user_input: Typed user input (UserInputDeferredTools) containing
                       approvals and/or external tool call results

        Returns:
            DeferredToolResults if user_input contains deferred tool data,
            None otherwise

        Note:
            The key invariant: Same ThreadProtocol events before/after approval
            must produce identical ModelMessages from transform(). Only the
            presence of DeferredToolResults should differ.
        """
        ...
