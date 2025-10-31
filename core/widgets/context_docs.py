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
from typing import TYPE_CHECKING
from dataclasses import dataclass
import fnmatch
import mimetypes

from core.widget import Widget

if TYPE_CHECKING:
    from core.protocols import ReadableThreadState
    from core.threadprotocol.blueprint import ComponentConfig


class ContentTooLargeError(Exception):
    """Raised when total context exceeds max_total_chars."""

    def __init__(self, total_chars: int, max_chars: int, file_path: str = None):
        self.total_chars = total_chars
        self.max_chars = max_chars
        self.file_path = file_path

        if file_path:
            message = (
                f"Content exceeds maximum of {max_chars:,} characters. "
                f"Total would be {total_chars:,} characters after including '{file_path}'"
            )
        else:
            message = f"Content exceeds maximum of {max_chars:,} characters. Total: {total_chars:,}"

        super().__init__(message)


@dataclass
class ContextDocsConfig:
    """Configuration for ContextDocsWidget.

    Stored in BlueprintProtocol (Turn 0 config).
    """
    base_path: str  # Base directory for file loading
    whitelist_paths: list[str]  # Patterns to include (e.g., "core/protocols/")
    blacklist_paths: list[str]  # Patterns to exclude (e.g., "*/archive/")
    max_total_chars: int = 400_000  # Maximum total characters (default: 400K)


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
        blacklist_paths: list[str] | None = None,
        max_total_chars: int = 400_000
    ):
        """Initialize ContextDocsWidget.

        Args:
            base_path: Base directory for file loading
            whitelist_paths: Patterns to include (e.g., "core/protocols/")
            blacklist_paths: Patterns to exclude (e.g., "*/archive/")
            max_total_chars: Maximum total characters across all files (default: 400K)

        Raises:
            ContentTooLargeError: If total content exceeds max_total_chars
        """
        super().__init__()

        self.base_path = Path(base_path)
        self.whitelist_paths = whitelist_paths
        self.blacklist_paths = blacklist_paths or []
        self.max_total_chars = max_total_chars

        # Load documents
        self.documents: dict[str, str] = {}
        self.total_chars = 0
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

    def _is_text_file(self, file_path: Path) -> bool:
        """Check if file is a text file based on extension and mime type.

        Args:
            file_path: Path to file

        Returns:
            True if file should be treated as text
        """
        # Skip files > 1MB (likely binary or generated)
        if file_path.exists():
            file_size = file_path.stat().st_size
            if file_size > 1_000_000:  # 1MB
                return False

        # Common text file extensions (80/20 rule)
        text_extensions = {
            # Source code
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.h',
            '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.sh',
            # Web
            '.html', '.css', '.xml', '.svg',
            # Data/Config
            '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.env',
            # Docs
            '.md', '.rst', '.txt',
            # Build
            '.dockerfile', '.makefile',
            # SQL
            '.sql',
        }

        # Check common filenames without extensions
        filename = file_path.name.lower()
        if filename in {'dockerfile', 'makefile', 'readme', 'license', 'changelog'}:
            return True

        # Check extension
        if file_path.suffix.lower() in text_extensions:
            return True

        # Fallback to mime type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type and mime_type.startswith('text/'):
            return True

        return False

    def _load_file_if_not_excluded(self, file_path: Path) -> None:
        """Load file if it passes all filters.

        Args:
            file_path: Absolute path to file

        Raises:
            ContentTooLargeError: If adding this file would exceed max_total_chars
        """
        # Get relative path from base
        try:
            rel_path = file_path.relative_to(self.base_path)
        except ValueError:
            # File is not under base_path, skip
            return

        # Always exclude hidden files/directories (starting with .)
        # Future: Add include_hidden parameter if override needed
        if any(part.startswith('.') for part in rel_path.parts):
            return  # Hidden file or in hidden directory

        # Check if excluded by user blacklist
        rel_path_str = str(rel_path)
        for exclude_pattern in self.blacklist_paths:
            if fnmatch.fnmatch(rel_path_str, exclude_pattern):
                return  # Excluded

        # Check if it's a text file
        if not self._is_text_file(file_path):
            return  # Binary file, skip

        # Load the file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check if adding this file would exceed limit
            content_length = len(content)
            new_total = self.total_chars + content_length

            if new_total > self.max_total_chars:
                raise ContentTooLargeError(
                    total_chars=new_total,
                    max_chars=self.max_total_chars,
                    file_path=rel_path_str
                )

            # Add to documents and update total
            self.documents[rel_path_str] = content
            self.total_chars = new_total

        except UnicodeDecodeError:
            # Not a text file despite our checks, skip silently
            return
        except ContentTooLargeError:
            # Re-raise content size errors
            raise
        except Exception as e:
            # Store error message for other failures
            error_msg = f"[Error loading {rel_path_str}: {str(e)}]"
            self.documents[rel_path_str] = error_msg
            self.total_chars += len(error_msg)

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

    def to_blueprint_config(self) -> 'ComponentConfig':
        """Serialize to BlueprintProtocol format.

        Returns:
            ComponentConfig with paths (content loaded at runtime)
        """
        from core.threadprotocol.blueprint import ComponentConfig

        config = {
            "base_path": str(self.base_path),
            "whitelist_paths": self.whitelist_paths.copy(),
            "blacklist_paths": self.blacklist_paths.copy()
        }

        # Only include max_total_chars if non-default
        if self.max_total_chars != 400_000:
            config["max_total_chars"] = self.max_total_chars

        return ComponentConfig(
            class_name=self.component_class_name,
            version=self.component_version,
            instance_id=self.instance_id or "context_docs_inst1",
            config=config
        )

    @classmethod
    def from_blueprint_config(cls, config: 'ComponentConfig') -> 'ContextDocsWidget':
        """Deserialize from BlueprintProtocol format.

        Args:
            config: ComponentConfig from Blueprint

        Returns:
            ContextDocsWidget instance with loaded documents
        """
        widget = cls(
            base_path=config.config["base_path"],
            whitelist_paths=config.config["whitelist_paths"],
            blacklist_paths=config.config.get("blacklist_paths", []),
            max_total_chars=config.config.get("max_total_chars", 400_000)
        )
        widget.instance_id = config.instance_id
        return widget
