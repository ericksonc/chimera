"""Space implementations for Chimera.

Spaces are execution environments for agents. They determine:
- Which agent(s) are active
- How message history is transformed (via transformers)
- Multi-agent orchestration patterns (if any)
"""

from .cron_summarizer_space import (
    AgentEval,
    CronSummarizerConfig,
    CronSummarizerSpace,
    SummaryOutput,
    length_check,
)
from .factory import SpaceFactory
from .generic_space import GenericSpace
from .graph_space import GraphSpace
from .roster_space import RosterSpace

__all__ = [
    "GenericSpace",
    "RosterSpace",
    "GraphSpace",
    "SpaceFactory",
    "CronSummarizerSpace",
    "CronSummarizerConfig",
    "SummaryOutput",
    "AgentEval",
    "length_check",
]
