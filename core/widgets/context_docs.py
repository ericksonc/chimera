"""ContextDocsWidget - Provides read-only context documents to agents.

This widget loads documents/code files from specified paths and makes them
available as ambient context (instructions) to the agent. It's read-only -
no tools, no state mutations.

Use cases:
- Project documentation
- Code snippets
- Guidelines and rules
- Architecture documentation
"""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass
import fnmatch

from core.widget import Widget

if TYPE_CHECKING:
    from core.protocols import ReadableThreadState
    from core.threadprotocol.blueprint import ComponentConfig


@dataclass
class ContextDocsConfig:
    """Configuration for ContextDocsWidget.

    Stored in BlueprintProtocol (Turn 0 config).
    """
    base_path: str  # Base directory for file loading
    whitelist_paths: list[str]  # Patterns to include (e.g., "core/protocols/")
    blacklist_paths: list[str]  # Patterns to exclude (e.g., "*/archive/")


class ContextDocsWidget(Widget[ContextDocsConfig]):
    """Provides context documents as ambient instructions.

    This is a stateless widget - files are loaded at initialization and
    provided via get_instructions() hook. No mutations, no tools.

    Example:
        widget = ContextDocsWidget(
            base_path="/Users/me/project",
            whitelist_paths=["core/protocols/", "docs/"],
            blacklist_paths=["*/archive/"]
        )

        agent.register_widget(widget)
    """

    # Component metadata
    component_class_name = "chimera.widgets.ContextDocsWidget"
    component_version = "1.0.0"

    def __init__(
        self,
        base_path: str,
        whitelist_paths: list[str],
        blacklist_paths: list[str] | None = None
    ):
        """Initialize ContextDocsWidget.

        Args:
            base_path: Base directory for file loading
            whitelist_paths: Patterns to include (e.g., "core/protocols/")
            blacklist_paths: Patterns to exclude (e.g., "*/archive/")
        """
        super().__init__()

        self.base_path = Path(base_path)
        self.whitelist_paths = whitelist_paths
        self.blacklist_paths = blacklist_paths or []

        # Load documents
        self.documents: dict[str, str] = {}
        self._load_documents()

    def _load_documents(self) -> None:
        """Load all matching documents from filesystem."""
        # Find all files matching whitelist patterns
        for pattern in self.whitelist_paths:
            # Convert gitignore-style patterns to paths
            # Support both "core/protocols/" and "core/protocols/**/*.py"
            if pattern.endswith('/'):
                # Directory pattern - get all files recursively
                search_path = self.base_path / pattern.rstrip('/')
                if search_path.exists() and search_path.is_dir():
                    for file_path in search_path.rglob('*'):
                        if file_path.is_file():
                            self._load_file_if_not_excluded(file_path)
            else:
                # Glob pattern
                for file_path in self.base_path.glob(pattern):
                    if file_path.is_file():
                        self._load_file_if_not_excluded(file_path)

    def _load_file_if_not_excluded(self, file_path: Path) -> None:
        """Load file if it doesn't match any blacklist patterns.

        Args:
            file_path: Absolute path to file
        """
        # Get relative path from base
        try:
            rel_path = file_path.relative_to(self.base_path)
        except ValueError:
            # File is not under base_path, skip
            return

        # Check if excluded
        rel_path_str = str(rel_path)
        for exclude_pattern in self.blacklist_paths:
            if fnmatch.fnmatch(rel_path_str, exclude_pattern):
                return  # Excluded

        # Load the file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.documents[rel_path_str] = content
        except Exception as e:
            # Store error message if loading fails
            self.documents[rel_path_str] = f"[Error loading {rel_path_str}: {str(e)}]"

    async def get_instructions(self, state: 'ReadableThreadState') -> str | None:
        """Provide context documents as instructions.

        Returns:
            Formatted context documents with file paths and contents
        """
        if not self.documents:
            return None

        # Build instructions
        lines = ["# CONTEXT DOCUMENTS", ""]

        for rel_path, content in sorted(self.documents.items()):
            lines.append(f"## File: {rel_path}")
            lines.append("")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)

    # ========================================================================
    # BlueprintProtocol Serialization
    # ========================================================================

    def to_blueprint_config(self) -> 'ComponentConfig[ContextDocsConfig]':
        """Serialize to BlueprintProtocol format.

        Returns:
            ComponentConfig with paths (content loaded at runtime)
        """
        from core.threadprotocol.blueprint import ComponentConfig

        return ComponentConfig(
            class_name=self.component_class_name,
            version=self.component_version,
            instance_id=self.instance_id or "context_docs_inst1",
            config=ContextDocsConfig(
                base_path=str(self.base_path),
                whitelist_paths=self.whitelist_paths.copy(),
                blacklist_paths=self.blacklist_paths.copy()
            )
        )

    @classmethod
    def from_blueprint_config(cls, config: 'ComponentConfig[ContextDocsConfig]') -> 'ContextDocsWidget':
        """Deserialize from BlueprintProtocol format.

        Args:
            config: ComponentConfig from Blueprint

        Returns:
            ContextDocsWidget instance with loaded documents
        """
        widget = cls(
            base_path=config.config.base_path,
            whitelist_paths=config.config.whitelist_paths,
            blacklist_paths=config.config.blacklist_paths
        )
        widget.instance_id = config.instance_id
        return widget
