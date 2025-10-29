"""Space implementations for Chimera.

Spaces are execution environments for agents. They determine:
- Which agent(s) are active
- How message history is transformed (via transformers)
- Multi-agent orchestration patterns (if any)
"""

from .generic_space import GenericSpace

__all__ = ["GenericSpace"]
