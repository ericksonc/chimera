"""Bash execution layer for Chimera agents.

This package provides three layers of bash command execution:

1. Executor Layer (executor.py):
   - BaseBashExecutor ABC: Pure command execution, no security
   - LocalBashExecutor: Local subprocess implementation

2. Security Layer (security.py):
   - AgentBashTools: Pattern validation (whitelist/blacklist modes)

3. Widget Layer (in core/widgets/):
   - EngineeringWidget: Direct bash access with blacklist
   - ManagerWidget: Safe bash with whitelist

The layered design allows:
- Swappable execution backends (local, Docker, SSH, K8s, etc.)
- Consistent security enforcement (whitelist or blacklist)
- Clean separation of concerns

Usage examples:

    # Whitelist mode (conservative - only allow specific commands):
    from chimera_core.primitives.bash import LocalBashExecutor, AgentBashTools
    from pathlib import Path

    executor = LocalBashExecutor()
    tools = AgentBashTools.create_whitelist(
        executor=executor,
        allowed_patterns=["^git ", "^ls ", "^pwd$"],
        cwd=Path("/Users/me/project")
    )
    result = await tools.execute("git status")

    # Blacklist mode (permissive - block dangerous commands):
    tools = AgentBashTools.create_blacklist(
        executor=executor,
        cwd=Path("/Users/me/project")
    )
    result = await tools.execute("npm test")  # OK
    # result = await tools.execute("rm -rf /")  # Blocked!
"""

from chimera_core.primitives.bash.executor import (
    BaseBashExecutor,
    BashResult,
    LocalBashExecutor,
)
from chimera_core.primitives.bash.security import (
    AgentBashTools,
    SecurityError,
)

__all__ = [
    "BaseBashExecutor",
    "LocalBashExecutor",
    "BashResult",
    "AgentBashTools",
    "SecurityError",
]
