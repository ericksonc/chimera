"""Space decision protocol for turn flow control.

This protocol allows Spaces to control multi-turn execution through thread.py's
pydantic-graph FSM. Spaces can orchestrate multiple agent turns by providing
decision logic and next prompts.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar, runtime_checkable

# TODO: Properly constrain this type variable based on PAI's AgentOutputT implementation
# For now, using unconstrained TypeVar to support str, int, float, Pydantic models, etc.
OutputT = TypeVar("OutputT")

# Type for decision routing (matches pydantic-graph's type matching pattern)
SpaceDecision = Literal["continue", "complete"]


@dataclass
class TurnDecision:
    """Decision from Space about whether to continue turns.

    Attributes:
        decision: "continue" to loop back to turn_start, "complete" to end thread
        next_prompt: Message for the next turn (required if continuing)
    """

    decision: SpaceDecision
    next_prompt: str = ""


@runtime_checkable
class DecidableSpace(Protocol):
    """Protocol for spaces that control multi-turn execution.

    Spaces implementing this protocol can orchestrate multiple agent turns
    by providing decision logic to thread.py's turn loop. The Space decides
    both whether to continue and what prompt to use for the next turn.

    Examples:
        GraphSpace: Executes nodes sequentially, provides node instructions
        GroupChatSpace: Round-robin agents, passes previous output as prompt
        OrchestratorSpace: Complex routing based on agent outputs
    """

    def should_continue_turn(self, last_output: OutputT) -> TurnDecision:
        """Determine if execution should continue to another turn.

        Called by thread.py's turn_complete step after each agent turn.
        The Space examines the last agent's output and its internal state
        to decide whether to continue execution.

        Args:
            last_output: The output from the agent that just completed
                        (can be str, int, float, Pydantic model, etc.)

        Returns:
            TurnDecision with:
            - decision: "continue" or "complete"
            - next_prompt: Instructions for next turn (required if continuing)
        """
        ...
