"""EngineeringWidget - Direct engineering capabilities for agents.

This widget provides agents with direct file and bash access, acting as an
alternative to Claude Code rather than managing it. The agent can directly
read, write, edit files and execute bash commands within a working directory.

Key features:
- Direct file access (read/write/edit) within cwd
- Bash execution with blacklist (dangerous commands blocked)
- Configurable approval mode (acceptEdits=True/False)
- No Claude Code dependency - agent does the work itself

Configuration:
- acceptEdits=True: Agent can write files without approval (like Claude Code)
- acceptEdits=False: Agent can read freely, but needs approval for writes
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ApprovalRequired

from chimera_core.agent import PAIDeps
from chimera_core.filesystem.editor import LocalFileEditor
from chimera_core.primitives.bash import AgentBashTools, LocalBashExecutor
from chimera_core.threadprotocol.blueprint import ComponentConfig
from chimera_core.widget import Widget

if TYPE_CHECKING:
    from pydantic_ai.toolsets import FunctionToolset

    # Using beta API for StepContext as pydantic-graph is still in beta
    # We accept the risk of breaking changes in future releases
    from pydantic_graph.beta import StepContext

    from chimera_core.agent import Agent
    from chimera_core.protocols import ReadableThreadState

logger = logging.getLogger(__name__)


class EngineeringWidget(Widget):
    """Widget that provides direct engineering capabilities to agents.

    This widget enables agents to work directly with files and bash,
    acting as an alternative to Claude Code (not managing it).

    **Available Tools:**
    - read_file(path): Read a file's contents (no approval needed)
    - write_file(path, content): Create or overwrite a file (approval if acceptEdits=False)
    - edit_file(path, old_string, new_string): Edit a file precisely (approval if acceptEdits=False)
    - edit_file(path, old_string, new_string): Edit a file precisely (approval if acceptEdits=False)
    - bash(command): Execute bash commands (blacklist dangerous patterns)

    **Configuration:**
    - acceptEdits: If True, agent can write without approval. If False, writes require approval.
    - cwd: Working directory for all operations
    - max_file_size: Maximum file size in bytes for reading

    **Security:**
    - All file operations restricted to cwd (no path traversal)
    - Bash commands checked against blacklist (rm -rf, dd, mkfs, etc.)
    - Approval required for writes when acceptEdits=False
    - Binary file protection (UTF-8 text files only)

    Example:
        # Full autonomy mode (like Claude Code with accept edits on)
        widget = EngineeringWidget(
            cwd="/Users/me/project",
            acceptEdits=True
        )

        # Review mode (agent asks permission for writes)
        widget = EngineeringWidget(
            cwd="/Users/me/project",
            acceptEdits=False
        )
    """

    # Component metadata
    component_version = "1.0.0"

    def __init__(
        self,
        cwd: Optional[str] = None,
        acceptEdits: bool = False,
        max_file_size: int = 200_000,
        bash_blacklist_patterns: Optional[list[str]] = None,
    ):
        """Initialize EngineeringWidget.

        Args:
            cwd: Working directory (Optional - if None, resolved from ClientContext)
            acceptEdits: If True, writes don't require approval. If False, they do.
            max_file_size: Maximum file size in bytes (default 200KB)
            bash_blacklist_patterns: Custom blacklist patterns (extends defaults)
        """
        super().__init__()
        self.cwd = Path(cwd).resolve() if cwd else None
        self.acceptEdits = acceptEdits
        self.max_file_size = max_file_size
        self.bash_blacklist_patterns = bash_blacklist_patterns

        # Initialize tools if cwd is known
        if self.cwd:
            self._init_tools(self.cwd)
        else:
            self.editor = None
            self.bash_tools = None

    def _init_tools(self, cwd: Path):
        """Initialize tools with a specific CWD."""
        # Validate cwd exists
        if not cwd.exists():
            raise ValueError(f"Working directory does not exist: {cwd}")
        if not cwd.is_dir():
            raise ValueError(f"Working directory must be a directory: {cwd}")

        # Initialize file editor
        self.editor = LocalFileEditor(base_path=str(cwd))

        # Initialize bash tools with blacklist mode
        bash_executor = LocalBashExecutor()
        self.bash_tools = AgentBashTools.create_blacklist(
            executor=bash_executor,
            blocked_patterns=self.bash_blacklist_patterns,  # Extends defaults
            cwd=cwd,
            timeout=60,
        )

    def _get_cwd(self, run_ctx: RunContext[PAIDeps]) -> Path:
        """Resolve CWD from self.cwd or ClientContext."""
        if self.cwd:
            return self.cwd

        # Try to get from ClientContext
        client_context = run_ctx.deps.client_context
        if client_context and "cwd" in client_context:
            cwd_str = client_context["cwd"]
            try:
                cwd = Path(cwd_str).resolve()
                if not cwd.exists() or not cwd.is_dir():
                    raise ValueError(f"Client CWD is invalid: {cwd}")
                return cwd
            except Exception as e:
                raise ValueError(f"Failed to resolve client CWD: {e}")

        raise ValueError(
            "Working directory not configured in widget or client context. "
            "Please provide 'cwd' in blueprint or ensure client sends it."
        )

    def _get_bash_tools(self, cwd: Path) -> AgentBashTools:
        """Get or create bash tools for the given CWD."""
        if self.bash_tools and self.cwd == cwd:
            return self.bash_tools

        # Create temporary tools for this CWD
        bash_executor = LocalBashExecutor()
        return AgentBashTools.create_blacklist(
            executor=bash_executor,
            blocked_patterns=self.bash_blacklist_patterns,
            cwd=cwd,
            timeout=60,
        )

    async def _execute_bash_command(self, ctx: RunContext[PAIDeps], command: str, cwd: Path) -> str:
        """Execute a bash command using the primitives layer.

        Args:
            ctx: Run context
            command: Command to execute
            cwd: Working directory

        Returns:
            Command output

        Raises:
            ModelRetry: If command fails
        """
        from pydantic_ai.exceptions import ModelRetry

        logger.info(f"[EngineeringWidget] Executing bash: {command}")
        bash_tools = self._get_bash_tools(cwd)

        try:
            # Execute via primitives layer (blacklist validation + execution)
            # ModelRetry is raised automatically for violations or failures
            result = await bash_tools.execute(command)
            return str(result.combined_output)
        except Exception as e:
            raise ModelRetry(f"Error executing bash command '{command}': {str(e)}")

    # ========================================================================
    # Path Validation
    # ========================================================================

    def _validate_path(self, path: str, cwd: Path) -> Path:
        """Validate path is within cwd, raise ModelRetry if not.

        Args:
            path: Relative or absolute path
            cwd: Working directory to validate against

        Returns:
            Resolved Path object within cwd

        Raises:
            ModelRetry: If path is outside working directory or invalid
        """
        from pydantic_ai.exceptions import ModelRetry

        # Handle both relative and absolute paths
        if Path(path).is_absolute():
            resolved = Path(path).resolve()
        else:
            resolved = (cwd / path).resolve()

        # Check if within cwd
        try:
            resolved.relative_to(cwd)
        except ValueError:
            raise ModelRetry(
                f"Path '{path}' is outside working directory.\n"
                f"Attempted: {resolved}\n"
                f"Allowed: {cwd}"
            )

        return resolved

    # ========================================================================
    # Widget Lifecycle
    # ========================================================================

    async def get_instructions(self, ctx: "StepContext") -> str | None:
        """Provide instructions about engineering capabilities.

        Args:
            ctx: Step context with state and deps (for resolving dynamic CWD)

        Returns:
            Instructions for using engineering tools
        """
        mode = "autonomous" if self.acceptEdits else "review"

        # Resolve CWD: use self.cwd if set, otherwise get from client_context
        display_cwd = self.cwd
        if display_cwd is None:
            client_context = ctx.deps.client_context
            if client_context and "cwd" in client_context:
                display_cwd = client_context["cwd"]

        lines = [
            "# Engineering Capabilities",
            "",
            f"You are working in **{mode} mode** with direct engineering access.",
            f"Working directory: {display_cwd}",
            "",
            "## File Operations",
            "",
            "**Available tools:**",
            "- `read_file(path)`: Read any file (no approval needed)",
            f"  - Max file size: {self.max_file_size:,} bytes",
            "  - Only UTF-8 text files supported",
            "- `write_file(path, content)`: Create or overwrite a file",
            "  - Parent directories created automatically",
        ]

        if self.acceptEdits:
            lines.append("  - **No approval needed** (autonomous mode)")
        else:
            lines.append("  - **Requires approval** (review mode)")

        lines.extend(
            [
                "- `edit_file(path, old_string, new_string)`: Edit a file precisely",
                "  - old_string must appear exactly once in the file",
            ]
        )

        if self.acceptEdits:
            lines.append("  - **No approval needed** (autonomous mode)")
        else:
            lines.append("  - **Requires approval** (review mode)")

        lines.extend(
            [
                "",
                "## Bash Execution",
                "",
                "- `bash(command)`: Execute shell commands in working directory",
                "  - Timeout: 60 seconds",
                "  - Dangerous commands blocked (rm -rf /, mkfs, reboot, etc.)",
                "  - Examples: git commands, npm/pip, find, grep, etc.",
                "",
                "## Important Notes",
                "",
                "- All paths are relative to working directory",
                "- Use forward slashes (e.g., `docs/readme.md`)",
                "- Path traversal (`..`) outside cwd is blocked",
                "- Dangerous bash commands are automatically blocked",
            ]
        )

        return "\n".join(lines)

    def get_toolset(self, ctx: "StepContext") -> Optional["FunctionToolset"]:
        """Provide engineering tools.

        Args:
            ctx: Step context with state and deps

        Returns:
            FunctionToolset with engineering tools
        """
        from pydantic_ai.exceptions import ModelRetry
        from pydantic_ai.toolsets import FunctionToolset

        toolset = FunctionToolset()

        @toolset.tool
        async def get_git_show(ctx: RunContext[PAIDeps], ref: str) -> str:
            """Show a git commit.

            Args:
                ref: The commit hash or reference to show

            Returns:
                The git show output
            """
            try:
                cwd = self._get_cwd(ctx)
                return str(await self._execute_bash_command(ctx, f"git show {ref}", cwd))
            except Exception as e:
                raise ModelRetry(f"Error getting git show: {str(e)}")

        @toolset.tool
        async def read_file(ctx: RunContext[PAIDeps], path: str) -> str:
            """Read the contents of a file.

            Use this tool to examine any file in your working directory.
            No approval required - you can read freely.

            Args:
                path: The path to the file to read (relative to CWD)

            Returns:
                The contents of the file
            """
            try:
                cwd = self._get_cwd(ctx)
                resolved_path = self._validate_path(path, cwd)

                if not resolved_path.exists():
                    raise ModelRetry(f"File not found: {path}")

                if not resolved_path.is_file():
                    raise ModelRetry(f"Path is not a file: {path}")

                # Check if binary
                try:
                    content = resolved_path.read_text()
                    size_bytes = len(content.encode("utf-8"))
                    if size_bytes > self.max_file_size:
                        raise ModelRetry(
                            f"File '{path}' is too large ({size_bytes:,} bytes). "
                            f"Maximum size is {self.max_file_size:,} bytes."
                        )
                    logger.info(f"[EngineeringWidget] Read file: {path} ({len(content)} chars)")
                    return content
                except UnicodeDecodeError:
                    raise ModelRetry(f"File appears to be binary: {path}")

            except Exception as e:
                raise ModelRetry(f"Error reading file '{path}': {str(e)}")

        @toolset.tool
        async def write_file(ctx: RunContext[PAIDeps], path: str, content: str) -> str:
            """Write content to a file (create new or overwrite existing).

            Use this tool to create new files or completely replace existing file contents.
            Requires approval if acceptEdits is False.

            Args:
                path: The path to the file to write (relative to CWD)
                content: The content to write to the file

            Returns:
                Success message
            """
            # Check approval if needed
            if not self.acceptEdits and not ctx.tool_call_approved:
                raise ApprovalRequired(f"Write file: {path}\nSize: {len(content)} chars")

            try:
                cwd = self._get_cwd(ctx)
                resolved_path = self._validate_path(path, cwd)

                # Create parent directories if needed
                resolved_path.parent.mkdir(parents=True, exist_ok=True)

                # Write file
                resolved_path.write_text(content)
                logger.info(f"[EngineeringWidget] Wrote file: {path} ({len(content)} chars)")
                return f"Successfully wrote to {path}"

            except ApprovalRequired:
                raise
            except Exception as e:
                raise ModelRetry(f"Error writing file '{path}': {str(e)}")

        @toolset.tool
        async def edit_file(
            ctx: RunContext[PAIDeps], path: str, old_string: str, new_string: str
        ) -> str:
            """Edit a file by replacing old_string with new_string.

            Use this tool to make precise edits to existing files. The old_string
            must appear exactly once in the file.

            Args:
                path: The path to the file to edit
                old_string: The exact string to replace (must be unique)
                new_string: The new string to replace it with

            Returns:
                Success message
            """
            # Check approval if needed
            if not self.acceptEdits and not ctx.tool_call_approved:
                raise ApprovalRequired(
                    f"Edit file: {path}\n"
                    f"Replace: '{old_string[:50]}...' with '{new_string[:50]}...'"
                )

            try:
                cwd = self._get_cwd(ctx)
                resolved_path = self._validate_path(path, cwd)

                if not resolved_path.exists():
                    raise ModelRetry(f"File not found: {path}")

                content = resolved_path.read_text()

                # Verify uniqueness
                count = content.count(old_string)
                if count == 0:
                    raise ModelRetry(
                        f"Could not find exact match for old_string in {path}. "
                        "Please check whitespace and formatting."
                    )
                if count > 1:
                    raise ModelRetry(
                        f"Found {count} occurrences of old_string in {path}. "
                        "Please provide more context to make it unique."
                    )

                # Replace
                new_content = content.replace(old_string, new_string)
                resolved_path.write_text(new_content)
                logger.info(f"[EngineeringWidget] Edited file: {path}")
                return f"Successfully edited {path}"

            except ApprovalRequired:
                raise
            except Exception as e:
                raise ModelRetry(f"Error editing file '{path}': {str(e)}")

        @toolset.tool
        async def bash(ctx: RunContext[PAIDeps], command: str) -> str:
            """Execute a bash command in the working directory.

            Use this tool to run shell commands for:
            - Git operations (status, diff, commit, push, etc.)
            - Package management (npm install, pip install, etc.)
            - File operations (ls, find, grep, wc, etc.)
            - Running tests, builds, or other scripts

            Dangerous commands are blocked (rm -rf /, mkfs, reboot, etc.).
            Commands timeout after 60 seconds.

            Args:
                command: Shell command to execute

            Returns:
                Command output (stdout + stderr, with exit code if non-zero)

            Raises:
                ModelRetry: If command is blacklisted, fails, or times out

            Examples:
                bash("ls -la")
                bash("git status")
                bash("npm test")
                bash("find . -name '*.py' | wc -l")
                bash("grep -r 'TODO' src/")
            """
            # Check approval if needed
            if not self.acceptEdits and not ctx.tool_call_approved:
                # Whitelist check for read-only commands could go here
                # For now, require approval for all bash commands if not acceptEdits
                raise ApprovalRequired(f"Execute bash: {command}")

            try:
                logger.info(f"[EngineeringWidget] Executing bash: {command}")

                cwd = self._get_cwd(ctx)
                bash_tools = self._get_bash_tools(cwd)

                # Execute via primitives layer (blacklist validation + execution)
                # ModelRetry is raised automatically for violations or failures
                result = await bash_tools.execute(command)
                return str(result.combined_output)

            except ApprovalRequired:
                raise
            except Exception as e:
                raise ModelRetry(f"Error executing bash command: {str(e)}")

        return toolset

    # ========================================================================
    # BlueprintProtocol Serialization
    # ========================================================================

    def _serialize_config(self) -> dict:
        """Serialize widget configuration to dict.

        Returns:
            Config dict with all widget parameters
        """
        return {
            "cwd": str(self.cwd) if self.cwd else None,
            "acceptEdits": self.acceptEdits,
            "max_file_size": self.max_file_size,
        }

    @classmethod
    def from_blueprint_config(cls, config: ComponentConfig, agent: "Agent") -> "EngineeringWidget":
        """Deserialize from BlueprintProtocol format.

        Args:
            config: ComponentConfig from Blueprint
            agent: Agent instance that owns this widget

        Returns:
            EngineeringWidget instance with configured settings
        """
        widget_config = config.config or {}

        cwd = widget_config.get("cwd")
        # cwd is optional now (can be None)

        widget = cls(
            cwd=cwd,
            acceptEdits=widget_config.get("acceptEdits", False),
            max_file_size=widget_config.get("max_file_size", 200_000),
        )
        widget.instance_id = config.instance_id
        return widget
