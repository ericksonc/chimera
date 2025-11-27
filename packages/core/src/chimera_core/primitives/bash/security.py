"""Security layer for bash execution - validation and sandboxing.

This module wraps BaseBashExecutor with security constraints:
- Command pattern validation (whitelist or blacklist mode)
- Working directory enforcement
- Timeout limits
- Agent-friendly error handling (ModelRetry exceptions)

The security layer is where we enforce command safety boundaries.
"""

import re
from pathlib import Path
from typing import Literal, Optional

from pydantic_ai.exceptions import ModelRetry

from chimera_core.primitives.bash.executor import BaseBashExecutor, BashResult


class SecurityError(Exception):
    """Raised when a security validation fails.

    This is an internal exception that gets converted to ModelRetry
    for agent consumption.
    """

    pass


class AgentBashTools:
    r"""Security wrapper for BaseBashExecutor with pattern validation.

    This class enforces:
    1. Command pattern validation - whitelist or blacklist mode
    2. Working directory enforcement - all executions in specified cwd
    3. Timeout limits - prevent long-running commands
    4. Agent-friendly errors - ModelRetry for retryable violations

    Two security modes:

    **Whitelist Mode** (Conservative - used by ManagerWidget):
    Only explicitly allowed command patterns can execute.
    Example: Only allow git, ls, wc, cat, etc.

    **Blacklist Mode** (Permissive - used by EngineeringWidget):
    All commands allowed except dangerous patterns.
    Example: Block rm -rf /, mkfs, reboot, etc.

    Example (whitelist mode):
        executor = LocalBashExecutor()
        tools = AgentBashTools(
            executor=executor,
            mode="whitelist",
            patterns=["^git ", "^ls ", "^pwd$"],
            cwd=Path("/Users/me/project"),
            timeout=60
        )

        # This will work (matches whitelist)
        result = await tools.execute("git status")

        # This will raise ModelRetry (not in whitelist)
        result = await tools.execute("rm -rf /")

    Example (blacklist mode):
        executor = LocalBashExecutor()
        tools = AgentBashTools(
            executor=executor,
            mode="blacklist",
            patterns=[r"rm\s+-rf\s+/", r"mkfs", r"reboot"],
            cwd=Path("/Users/me/project"),
            timeout=60
        )

        # This will work (not in blacklist)
        result = await tools.execute("npm test")

        # This will raise ModelRetry (matches blacklist)
        result = await tools.execute("rm -rf /")
    """

    # Default dangerous command patterns (for blacklist mode)
    DEFAULT_BLACKLIST = [
        r"rm\s+-rf\s+/",  # Recursive force delete from root
        r"rm\s+-rf\s+~",  # Recursive force delete home
        r"mkfs",  # Format filesystem
        r"dd\s+.*of=/dev/",  # Write to block devices
        r":(){ :|:& };:",  # Fork bomb
        r"chmod\s+-R\s+777",  # Dangerous permissions
        r"wget.*\|\s*sh",  # Download and execute
        r"curl.*\|\s*sh",  # Download and execute
        r">\s*/dev/sd[a-z]",  # Write to disk devices
        r"mkswap",  # Create swap
        r"swapon",  # Enable swap
        r"swapoff",  # Disable swap
        r"reboot",  # System reboot
        r"shutdown",  # System shutdown
        r"init\s+[0-6]",  # Change runlevel
        r"systemctl\s+(halt|poweroff|reboot)",  # Systemctl power commands
    ]

    def __init__(
        self,
        executor: BaseBashExecutor,
        mode: Literal["whitelist", "blacklist"],
        patterns: list[str],
        cwd: Path,
        timeout: int = 60,
    ):
        """Initialize AgentBashTools with security constraints.

        Args:
            executor: BaseBashExecutor implementation to wrap
            mode: Security mode - "whitelist" (only allow patterns) or "blacklist" (block patterns)
            patterns: List of regex patterns for validation
            cwd: Working directory for all executions
            timeout: Timeout in seconds (default 60)
        """
        self.executor = executor
        self.mode = mode
        self.patterns = patterns
        self.cwd = Path(cwd).resolve()
        self.timeout = timeout

        # Validate cwd exists
        if not self.cwd.exists():
            raise ValueError(f"Working directory does not exist: {cwd}")
        if not self.cwd.is_dir():
            raise ValueError(f"Working directory must be a directory: {cwd}")

    def _validate_command(self, command: str) -> None:
        """Validate command against patterns based on mode.

        Args:
            command: Shell command to validate

        Raises:
            SecurityError: If command violates security policy
        """
        cmd = command.strip()

        if self.mode == "whitelist":
            # Whitelist mode: command must match at least one pattern
            matches = any(re.search(pattern, cmd, re.IGNORECASE) for pattern in self.patterns)
            if not matches:
                raise SecurityError(
                    f"Command not in whitelist: `{cmd}`\n\n"
                    f"This command is not on the allowed list. "
                    f"Please use one of the allowed command patterns:\n"
                    f"{self._format_patterns_for_agent()}\n\n"
                    f"If you need to run this command, please ask the user for approval."
                )

        elif self.mode == "blacklist":
            # Blacklist mode: command must not match any pattern
            for pattern in self.patterns:
                if re.search(pattern, cmd, re.IGNORECASE):
                    raise SecurityError(
                        f"Dangerous command blocked: `{cmd}`\n"
                        f"Matched blacklist pattern: {pattern}\n\n"
                        f"This command is blocked for safety. "
                        f"If you need to perform this operation, please ask the user."
                    )

    def _format_patterns_for_agent(self) -> str:
        """Format patterns in a human-readable way for agent feedback."""
        if not self.patterns:
            return "(no patterns configured)"

        # Convert regex patterns to readable descriptions
        readable = []
        for pattern in self.patterns[:10]:  # Limit to first 10
            # Clean up common regex patterns for readability
            clean = pattern.replace("^", "").replace("$", "").replace("\\s+", " ")
            readable.append(f"  - {clean}")

        if len(self.patterns) > 10:
            readable.append(f"  ... and {len(self.patterns) - 10} more patterns")

        return "\n".join(readable)

    async def execute(self, command: str, timeout: Optional[int] = None) -> BashResult:
        """Execute a bash command with security checks.

        Args:
            command: Shell command to execute
            timeout: Optional timeout override (uses default if not specified)

        Returns:
            BashResult with stdout, stderr, and exit code

        Raises:
            ModelRetry: If command violates security policy or execution fails
        """
        # Validate command against patterns
        try:
            self._validate_command(command)
        except SecurityError as e:
            # Convert to ModelRetry for agent consumption
            raise ModelRetry(str(e))

        # Execute with security constraints
        try:
            result = await self.executor.execute(
                command=command,
                cwd=self.cwd,
                timeout=timeout or self.timeout,
            )
            return result

        except Exception as e:
            # Convert execution errors to ModelRetry
            raise ModelRetry(f"Command execution failed: {command}\nError: {str(e)}")

    @classmethod
    def create_whitelist(
        cls,
        executor: BaseBashExecutor,
        allowed_patterns: list[str],
        cwd: Path,
        timeout: int = 60,
    ) -> "AgentBashTools":
        """Convenience factory for whitelist mode.

        Args:
            executor: BaseBashExecutor implementation
            allowed_patterns: List of allowed command patterns (regex)
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            AgentBashTools configured in whitelist mode
        """
        return cls(
            executor=executor,
            mode="whitelist",
            patterns=allowed_patterns,
            cwd=cwd,
            timeout=timeout,
        )

    @classmethod
    def create_blacklist(
        cls,
        executor: BaseBashExecutor,
        blocked_patterns: Optional[list[str]] = None,
        cwd: Path = None,
        timeout: int = 60,
    ) -> "AgentBashTools":
        """Convenience factory for blacklist mode.

        Args:
            executor: BaseBashExecutor implementation
            blocked_patterns: List of blocked patterns (extends defaults if provided)
            cwd: Working directory (defaults to current directory)
            timeout: Timeout in seconds

        Returns:
            AgentBashTools configured in blacklist mode with default dangerous patterns
        """
        # Start with default blacklist
        patterns = cls.DEFAULT_BLACKLIST.copy()

        # Extend with custom patterns if provided
        if blocked_patterns:
            patterns.extend(blocked_patterns)

        return cls(
            executor=executor,
            mode="blacklist",
            patterns=patterns,
            cwd=cwd or Path.cwd(),
            timeout=timeout,
        )
