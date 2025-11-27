"""Filesystem access layer for Chimera agents.

This package provides three layers of filesystem access:

1. Editor Layer (editor.py):
   - BaseFileEditor ABC: Pure I/O operations, no security
   - LocalFileEditor: Local filesystem implementation

2. Security Layer (security.py):
   - AgentFileTools: Sandboxing, validation, size limits

3. Widget Layer (in core/widgets/filesystem_widget.py):
   - FileSystemWidget: Chimera widget integration with tools

The layered design allows:
- Swappable storage backends (local, cloud, git, etc.)
- Consistent security enforcement
- Clean separation of concerns
"""

from chimera_core.filesystem.editor import BaseFileEditor, LocalFileEditor
from chimera_core.filesystem.security import AgentFileTools, SecurityError

__all__ = [
    "BaseFileEditor",
    "LocalFileEditor",
    "AgentFileTools",
    "SecurityError",
]
