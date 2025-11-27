"""ClaudeCodeWidget - Provides access to Claude Code as a tool.

This widget enables Chimera agents to delegate tasks to Claude Code, maintaining
conversation continuity across turns via resume_id persistence.

Version 1.1 adds:
- Configurable tool permissions
- Bash command safety patterns
- Cost tracking and budget limits
- Hook system for observability
- Asyncio cancellation handling

Version 1.2 adds:
- Real-time streaming with data-app-claude events
- Text-complete, thinking-complete, tool-use-complete event emission
- Session-complete event with cost/duration metrics
"""

import asyncio
import csv
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal, Optional

from chimera_core.threadprotocol.blueprint import ComponentConfig
from chimera_core.ui.app_events import (
    ClaudeEventData,
    ClaudeSessionCompletePayload,
    ClaudeTextCompletePayload,
    ClaudeThinkingCompletePayload,
    ClaudeToolUseCompletePayload,
    DataAppClaudeEvent,
)
from chimera_core.widget import StatefulWidget

if TYPE_CHECKING:
    from pydantic_ai.toolsets import FunctionToolset

    from chimera_core.agent import Agent
    from chimera_core.step_context import StepContext

logger = logging.getLogger(__name__)


class StreamingState:
    """Tracks Claude Code streaming state to emit complete blocks.

    Assumptions:
    - Anthropic SDK emits events in strict order: content_block_start → delta* → content_block_stop
    - Block indices are unique and sequential within a message
    - No duplicate or out-of-order events for the same index

    If these assumptions are violated, events are logged and skipped gracefully.
    """

    def __init__(self):
        self.blocks: dict[int, dict] = {}  # index → block data

    def handle_stream_event(self, event) -> dict | None:
        """Process stream event, return complete block event if ready.

        Args:
            event: StreamEvent from Claude Code SDK

        Returns:
            Event data dict if block is complete, None otherwise
        """
        anthropic_event = event.event
        event_type = anthropic_event.get("type")

        if event_type == "content_block_start":
            # Track new block
            index = anthropic_event["index"]
            block = anthropic_event["content_block"]
            self.blocks[index] = {
                "type": block["type"],
                "accumulated_content": "",
                "tool_data": {} if block["type"] == "tool_use" else None,
            }

            if block["type"] == "tool_use":
                self.blocks[index]["tool_data"] = {
                    "id": block["id"],
                    "name": block["name"],
                    "input_json": "",
                }

        elif event_type == "content_block_delta":
            # Accumulate content
            index = anthropic_event["index"]

            # Defensive: Skip if block not initialized (missing start event)
            if index not in self.blocks:
                logger.warning(
                    f"[StreamingState] Received delta for uninitialized block {index}, skipping"
                )
                return None

            delta = anthropic_event["delta"]

            if delta["type"] == "text_delta":
                self.blocks[index]["accumulated_content"] += delta["text"]
            elif delta["type"] == "thinking_delta":
                self.blocks[index]["accumulated_content"] += delta["thinking"]
            elif delta["type"] == "input_json_delta":
                self.blocks[index]["tool_data"]["input_json"] += delta["partial_json"]

        elif event_type == "content_block_stop":
            # Block complete! Emit event
            index = anthropic_event["index"]

            # Defensive: Use pop with None check
            block = self.blocks.pop(index, None)
            if block is None:
                logger.warning(
                    f"[StreamingState] Received stop for uninitialized block {index}, skipping"
                )
                return None

            return self._create_complete_event(index, block, event.session_id)

        return None

    def _create_complete_event(self, index: int, block: dict, session_id: str) -> dict:
        """Create event data for completed block using typed models.

        Returns dict with eventType and payload fields (not the full VSP event).
        Uses Pydantic models for type safety and validation.
        """
        block_type = block["type"]

        if block_type == "text":
            payload = ClaudeTextCompletePayload(
                index=index, text=block["accumulated_content"], block_type="text"
            )
            return {"eventType": "text-complete", "payload": payload.model_dump(by_alias=True)}

        elif block_type == "thinking":
            payload = ClaudeThinkingCompletePayload(
                index=index, thinking=block["accumulated_content"], block_type="thinking"
            )
            return {"eventType": "thinking-complete", "payload": payload.model_dump(by_alias=True)}

        elif block_type == "tool_use":
            tool_data = block["tool_data"]
            payload = ClaudeToolUseCompletePayload(
                index=index,
                tool_call_id=tool_data["id"],
                tool_name=tool_data["name"],
                input=json.loads(tool_data["input_json"]),
                block_type="tool_use",
            )
            return {"eventType": "tool-use-complete", "payload": payload.model_dump(by_alias=True)}


@dataclass
class UsageLog:
    """Tracks usage and cost data for Claude Code interactions."""

    timestamp: str
    thread_id: str
    blueprint_id: str
    agent_name: str
    agent_id: str
    resume_id: str
    cwd: str
    prompt_tokens: int
    completion_tokens: int
    total_cost_usd: float


@dataclass
class ClaudeCodeHook:
    """Hook for intercepting and modifying Claude Code tool usage."""

    event: Literal["PreToolUse", "PostToolUse"]
    matcher: Optional[str] = None  # Tool name pattern to match
    callback: Optional[Callable] = None  # Async callback(tool_name, params) -> params


@dataclass
class ClaudeCodeMutation:
    """Mutation for updating Claude Code session state."""

    action: Literal["set_resume_id", "log_usage"]
    resume_id: Optional[str] = None  # UUID from Claude Code SDK (ResultMessage.session_id)
    usage_log: Optional[UsageLog] = None  # Usage/cost tracking data


class ClaudeCodeWidget(StatefulWidget[ComponentConfig, ClaudeCodeMutation]):
    """Widget providing Claude Code as a tool with conversation continuity.

    This widget:
    - Exposes query_claude_code tool to Chimera agents
    - Persists resume_id (Claude Code session UUID) for conversation continuity
    - Supports shared (space-level) or private (agent-level) conversations
    - Tracks usage and costs with configurable budget limits
    - Provides hook system for observability and guardrails

    Configuration:
        shared_instance: bool
            - False (default): Agent-level widget, each agent has own Claude Code conversation
            - True: Space-level widget, all agents share same Claude Code conversation

        Tool Permissions:
            - allowed_tools: Whitelist of tool names (None = all tools allowed)
            - disallowed_tools: Blacklist of tool names (overrides allowed_tools)

        Bash Safety:
            - bash_allow_patterns: Regex whitelist for bash commands
            - bash_block_patterns: Regex blacklist (raises error)
            - bash_dry_run_patterns: Commands that get --dry-run flag added

        Budget Controls:
            - max_budget_usd: Maximum cost per session (None = unlimited)
            - max_turns: Maximum conversation turns

    State:
        resume_id: str | None
            - Claude Code session UUID for resuming conversations
            - Persisted via StatefulWidget mutation pattern
        total_cost_usd: float
            - Accumulated cost for this session
        usage_logs: list[UsageLog]
            - History of all Claude Code interactions with costs
    """

    # component_class_name auto-generated by PluginMeta as "core.widgets.claude_code_widget.ClaudeCodeWidget"
    component_version = "1.2.0"

    def __init__(
        self,
        cwd: str,
        shared_instance: bool = False,
        # Tool permissions (v1.1)
        allowed_tools: Optional[list[str]] = None,
        disallowed_tools: Optional[list[str]] = None,
        # Bash safety patterns (v1.1)
        bash_allow_patterns: Optional[list[str]] = None,
        bash_block_patterns: Optional[list[str]] = None,
        bash_dry_run_patterns: Optional[list[str]] = None,
        # Budget controls (v1.1)
        max_budget_usd: Optional[float] = None,
        max_turns: int = 10,
        # Observability (v1.1)
        hooks: Optional[list[ClaudeCodeHook]] = None,
        usage_log_file: Optional[str] = None,
    ):
        """Initialize ClaudeCodeWidget.

        Args:
            cwd: Working directory for Claude Code operations (required).
                 Claude Code will be sandboxed to this directory.
            shared_instance: If True, conversation shared across agents (space-level).
                           If False, each agent has private conversation (agent-level).
            allowed_tools: List of tool names to allow. None = all tools allowed.
                         Default: ["Read", "Write", "Bash", "Edit", "Glob", "Grep"]
            disallowed_tools: List of tool names to block. Overrides allowed_tools.
            bash_allow_patterns: Regex patterns for bash commands to allow.
            bash_block_patterns: Regex patterns for bash commands to block (raises error).
            bash_dry_run_patterns: Regex patterns for bash commands that get --dry-run added.
            max_budget_usd: Maximum cost in USD. None = unlimited. Default: None.
            max_turns: Maximum conversation turns. Default: 10.
            hooks: List of hooks for observability. Default: None.
            usage_log_file: Path to TSV file for usage logging.
                          Default: /Users/ericksonc/chimera-desktop/logs/claude_usage.tsv
        """
        super().__init__()
        self.cwd = cwd
        self.shared_instance = shared_instance

        # Tool permissions
        self.allowed_tools = allowed_tools or ["Read", "Write", "Bash", "Edit", "Glob", "Grep"]
        self.disallowed_tools = disallowed_tools or []

        # Bash safety patterns
        self.bash_allow_patterns = bash_allow_patterns or []
        self.bash_block_patterns = bash_block_patterns or [
            r"sudo",  # No sudo by default
            r"^\s*>",  # No output redirection
        ]
        self.bash_dry_run_patterns = bash_dry_run_patterns or [
            r"rm\s+-rf",  # Force delete → interactive
            r"chmod\s+-R\s+777",  # Recursive permission change
        ]

        # Budget controls
        self.max_budget_usd = max_budget_usd
        self.max_turns = max_turns

        # Observability
        self.hooks = hooks or []
        self.usage_log_file = Path(
            usage_log_file or "/Users/ericksonc/chimera-desktop/logs/claude_usage.tsv"
        )

        # State (persisted via mutations)
        self.resume_id: Optional[str] = None
        self.total_cost_usd: float = 0.0
        self.usage_logs: list[UsageLog] = []

        # Will be captured from ctx in get_toolset
        self._emit_threadprotocol_event = None
        self._event_loop = None

    def _get_effective_tools(self) -> list[str]:
        """Get effective tool list after applying allowed/disallowed filters."""
        tools = self.allowed_tools.copy()
        # Remove disallowed tools
        return [t for t in tools if t not in self.disallowed_tools]

    async def _invoke_hooks(
        self, event: str, tool_name: str = "query", params: dict = None
    ) -> dict:
        """Invoke registered hooks for given event.

        Args:
            event: Hook event type ("PreToolUse" or "PostToolUse")
            tool_name: Name of tool being used
            params: Tool parameters (will be modified by hooks)

        Returns:
            Modified params dict
        """
        params = params or {}

        for hook in self.hooks:
            if hook.event != event:
                continue

            # Check matcher if specified
            if hook.matcher and tool_name != hook.matcher:
                continue

            # Invoke callback if present
            if hook.callback:
                try:
                    result = hook.callback(tool_name, params)
                    if asyncio.iscoroutine(result):
                        params = await result
                    else:
                        params = result
                    logger.debug(f"[ClaudeCodeWidget] Hook {hook.event} for {tool_name} executed")
                except Exception as e:
                    logger.error(f"[ClaudeCodeWidget] Hook callback failed: {e}", exc_info=True)

        return params

    def _check_bash_safety(self, command: str) -> str:
        """Check bash command against safety patterns.

        Args:
            command: The bash command to check

        Returns:
            Modified command (potentially with --dry-run added)

        Raises:
            ValueError: If command matches block patterns
        """
        # Check block patterns
        for pattern in self.bash_block_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                raise ValueError(f"Blocked bash command matching pattern '{pattern}': {command}")

        # Check dry-run patterns - modify command
        for pattern in self.bash_dry_run_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                logger.warning(
                    f"[ClaudeCodeWidget] Adding safety flag to command matching '{pattern}'"
                )
                # Simple modification - add interactive flag
                if "rm -rf" in command:
                    command = command.replace("rm -rf", "rm -ri")
                break

        return command

    async def _append_usage_file(self, usage_log: UsageLog) -> None:
        """Append usage data to TSV file for SQL import."""
        try:
            self.usage_log_file.parent.mkdir(parents=True, exist_ok=True)

            # Create header if file doesn't exist
            if not self.usage_log_file.exists():
                with open(self.usage_log_file, "w", newline="") as f:
                    writer = csv.writer(f, delimiter="\t")
                    writer.writerow(
                        [
                            "timestamp",
                            "thread_id",
                            "blueprint_id",
                            "agent_name",
                            "agent_id",
                            "resume_id",
                            "cwd",
                            "prompt_tokens",
                            "completion_tokens",
                            "total_cost_usd",
                        ]
                    )

            # Append usage record
            with open(self.usage_log_file, "a", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(
                    [
                        usage_log.timestamp,
                        usage_log.thread_id,
                        usage_log.blueprint_id,
                        usage_log.agent_name,
                        usage_log.agent_id,
                        usage_log.resume_id,
                        usage_log.cwd,
                        usage_log.prompt_tokens,
                        usage_log.completion_tokens,
                        usage_log.total_cost_usd,
                    ]
                )
            logger.debug(f"[ClaudeCodeWidget] Logged usage to {self.usage_log_file}")
        except Exception as e:
            logger.error(f"[ClaudeCodeWidget] Failed to write usage log: {e}", exc_info=True)

    def get_toolset(self, ctx: "StepContext") -> Optional["FunctionToolset"]:
        """Provide query_claude_code tool.

        Args:
            ctx: Step context with deps for mutation emission

        Returns:
            FunctionToolset with query_claude_code tool
        """
        from pydantic_ai.toolsets import FunctionToolset

        # Capture emit function and event loop for mutation emission
        # (Tools run in worker threads, so we need the loop from async context)
        self._emit_threadprotocol_event = ctx.deps.emit_threadprotocol_event
        self._event_loop = asyncio.get_running_loop()
        logger.debug(
            f"[ClaudeCodeWidget] Captured emit function and event loop for instance {self.instance_id}"
        )

        toolset = FunctionToolset()

        @toolset.tool
        async def query_claude_code(prompt: str, max_turns: Optional[int] = None) -> str:
            """Delegate a task to Claude Code. Continues previous conversation if any.

            Use this tool to:
            - Perform complex multi-step tasks
            - Work with files and directories
            - Execute shell commands
            - Analyze codebases
            - Refactor or generate code

            Claude Code has access to configured tools within the working directory.
            Cost tracking is enabled and budget limits are enforced if configured.

            Args:
                prompt: The task or question for Claude Code
                max_turns: Maximum conversation turns (default from widget config)

            Returns:
                Claude Code's response as text
            """
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                CLINotFoundError,
                ProcessError,
                ResultMessage,
                TextBlock,
                query,
            )
            from claude_agent_sdk.types import StreamEvent

            # Check budget before starting
            if self.max_budget_usd and self.total_cost_usd >= self.max_budget_usd:
                return f"Error: Budget limit reached. Total cost: ${self.total_cost_usd:.4f}, Limit: ${self.max_budget_usd:.2f}"

            # Use widget default max_turns if not specified
            effective_max_turns = max_turns if max_turns is not None else self.max_turns

            # Invoke PreToolUse hooks
            hook_params = {
                "prompt": prompt,
                "max_turns": effective_max_turns,
                "cwd": self.cwd,
                "resume_id": self.resume_id,
            }
            hook_params = await self._invoke_hooks("PreToolUse", "claude_code", hook_params)

            # Build options with configured tools
            options = ClaudeAgentOptions(
                allowed_tools=self._get_effective_tools(),
                permission_mode="acceptEdits",  # Auto-accept file edits
                cwd=self.cwd,  # Use configured working directory
                max_turns=effective_max_turns,
                resume=self.resume_id,  # Continue conversation if we have a session
                include_partial_messages=True,  # Enable streaming events (v1.2)
            )

            logger.info(
                f"[ClaudeCodeWidget] Querying Claude Code with resume_id={self.resume_id}, "
                f"tools={self._get_effective_tools()}, max_turns={effective_max_turns}"
            )

            # Accumulate response and track streaming state (v1.2)
            response_text = []
            new_resume_id = None
            usage_data = None
            streaming_state = StreamingState()

            try:
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, StreamEvent):
                        # Process stream event, emit if block complete (v1.2)
                        complete_event_data = streaming_state.handle_stream_event(message)

                        if complete_event_data:
                            # Emit data-app-claude event using typed model
                            event_data = ClaudeEventData(
                                source=self._get_event_source(),
                                claude_session_id=message.session_id,
                                event_type=complete_event_data["eventType"],
                                payload=complete_event_data["payload"],
                            )
                            event_model = DataAppClaudeEvent(
                                type="data-app-claude", transient=True, data=event_data
                            )
                            event = event_model.model_dump(by_alias=True)

                            if self._emit_threadprotocol_event and self._event_loop:
                                asyncio.run_coroutine_threadsafe(
                                    self._emit_threadprotocol_event(event), self._event_loop
                                )
                            else:
                                logger.error(
                                    f"[ClaudeCodeWidget] Cannot emit {complete_event_data['eventType']} event - "
                                    "missing emit function or event loop. Ensure get_toolset() was called before tool execution."
                                )

                    elif isinstance(message, AssistantMessage):
                        # Extract text from assistant messages
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                response_text.append(block.text)

                    elif isinstance(message, ResultMessage):
                        # Extract session_id and usage data
                        new_resume_id = message.session_id
                        logger.info(
                            f"[ClaudeCodeWidget] Got ResultMessage with session_id={new_resume_id}"
                        )

                        # Emit session-complete event (v1.2) using typed model
                        payload = ClaudeSessionCompletePayload(
                            num_turns=message.num_turns,
                            duration_ms=message.duration_ms,
                            total_cost_usd=getattr(message, "total_cost_usd", 0.0),
                            is_error=message.is_error,
                        )
                        event_data = ClaudeEventData(
                            source=self._get_event_source(),
                            claude_session_id=message.session_id,
                            event_type="session-complete",
                            payload=payload.model_dump(by_alias=True),
                        )
                        event_model = DataAppClaudeEvent(
                            type="data-app-claude", transient=True, data=event_data
                        )
                        session_complete_event = event_model.model_dump(by_alias=True)

                        if self._emit_threadprotocol_event and self._event_loop:
                            asyncio.run_coroutine_threadsafe(
                                self._emit_threadprotocol_event(session_complete_event),
                                self._event_loop,
                            )
                        else:
                            logger.error(
                                "[ClaudeCodeWidget] Cannot emit session-complete event - "
                                "missing emit function or event loop. Ensure get_toolset() was called before tool execution."
                            )

                        # Extract cost data if available
                        if hasattr(message, "usage") and message.usage:
                            usage = message.usage
                            usage_data = UsageLog(
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                thread_id=ctx.thread_id if hasattr(ctx, "thread_id") else "unknown",
                                blueprint_id=ctx.blueprint_id
                                if hasattr(ctx, "blueprint_id")
                                else "unknown",
                                agent_name=self.agent.identifier if self.agent else "unknown",
                                agent_id=str(self.agent.id) if self.agent else "unknown",
                                resume_id=new_resume_id or "unknown",
                                cwd=self.cwd,
                                prompt_tokens=getattr(usage, "input_tokens", 0),
                                completion_tokens=getattr(usage, "output_tokens", 0),
                                total_cost_usd=getattr(usage, "total_cost_usd", 0.0),
                            )
                            logger.info(
                                f"[ClaudeCodeWidget] Usage: {usage_data.prompt_tokens} input, "
                                f"{usage_data.completion_tokens} output, ${usage_data.total_cost_usd:.4f}"
                            )

            except asyncio.CancelledError:
                # User cancelled - log and re-raise for proper propagation
                logger.warning("[ClaudeCodeWidget] Task cancelled by user")
                raise
            except CLINotFoundError:
                return "Error: Claude Code CLI not installed. Install with: npm install -g @anthropic-ai/claude-code"
            except ProcessError as e:
                return f"Error: Claude Code failed with exit code {e.exit_code}"
            except Exception as e:
                logger.error(f"[ClaudeCodeWidget] Unexpected error: {e}", exc_info=True)
                return f"Error: {type(e).__name__}: {e}"

            # Persist resume_id via mutation if we got a new one
            if new_resume_id and new_resume_id != self.resume_id:
                mutation = ClaudeCodeMutation(action="set_resume_id", resume_id=new_resume_id)
                self.mutate(mutation)  # Saves to ThreadProtocol then applies
                logger.info(f"[ClaudeCodeWidget] Persisted new resume_id={new_resume_id}")

            # Persist usage data if we got it
            if usage_data:
                mutation = ClaudeCodeMutation(action="log_usage", usage_log=usage_data)
                self.mutate(mutation)  # Saves to ThreadProtocol then applies

                # Also append to file for SQL import
                await self._append_usage_file(usage_data)

                # Update total cost
                self.total_cost_usd += usage_data.total_cost_usd

                # Warn if approaching budget limit
                if self.max_budget_usd:
                    pct_used = (self.total_cost_usd / self.max_budget_usd) * 100
                    if pct_used >= 80:
                        logger.warning(
                            f"[ClaudeCodeWidget] Budget warning: {pct_used:.1f}% used "
                            f"(${self.total_cost_usd:.4f} / ${self.max_budget_usd:.2f})"
                        )

            # Invoke PostToolUse hooks
            post_params = {
                "prompt": prompt,
                "response": "\n".join(response_text) if response_text else "No response",
                "resume_id": new_resume_id,
                "cost_usd": usage_data.total_cost_usd if usage_data else 0.0,
            }
            await self._invoke_hooks("PostToolUse", "claude_code", post_params)

            # Return accumulated response
            result = "\n".join(response_text) if response_text else "No response"
            return result

        return toolset

    # ========================================================================
    # StatefulWidget Contract - Mutation Management
    # ========================================================================

    def save_mutation(self, mutation: ClaudeCodeMutation) -> None:
        """Save mutation to ThreadProtocol.

        v0.0.7: Writes a data-app-chimera event with nested structure:
        {
            "type": "data-app-chimera",
            "data": {
                "source": "widget:ClaudeCodeWidget:{instance_id}",
                "payload": {mutation serialized to dict}
            }
        }

        Args:
            mutation: The mutation to save
        """
        logger.debug(f"[ClaudeCodeWidget] save_mutation called: {asdict(mutation)}")

        if not self._emit_threadprotocol_event:
            logger.warning(
                "[ClaudeCodeWidget] No emit function available - mutation will be DROPPED!"
            )
            return

        # Create event data (v0.0.7: nested data structure)
        event = {
            "type": "data-app-chimera",
            "data": {"source": self._get_event_source(), "payload": asdict(mutation)},
        }

        # Emit to ThreadProtocol
        # Tools run in worker threads, so use run_coroutine_threadsafe
        if not self._event_loop:
            logger.error(
                "[ClaudeCodeWidget] No event loop captured! Cannot emit from worker thread."
            )
            return

        asyncio.run_coroutine_threadsafe(self._emit_threadprotocol_event(event), self._event_loop)
        logger.debug("[ClaudeCodeWidget] Mutation saved to ThreadProtocol")

    def apply_mutation(self, mutation: ClaudeCodeMutation | dict) -> None:
        """Apply mutation to local state.

        Args:
            mutation: The mutation to apply (typed or dict from replay)
        """
        # Handle dict input (from ThreadProtocol replay)
        if isinstance(mutation, dict):
            # Convert usage_log dict to UsageLog if present
            if mutation.get("action") == "log_usage" and mutation.get("usage_log"):
                usage_log_dict = mutation["usage_log"]
                mutation["usage_log"] = UsageLog(**usage_log_dict)
            mutation = ClaudeCodeMutation(**mutation)

        logger.debug(f"[ClaudeCodeWidget] apply_mutation: {mutation.action}")

        if mutation.action == "set_resume_id":
            self.resume_id = mutation.resume_id
            logger.debug(f"[ClaudeCodeWidget] Applied resume_id={self.resume_id}")
        elif mutation.action == "log_usage":
            if mutation.usage_log:
                self.usage_logs.append(mutation.usage_log)
                self.total_cost_usd += mutation.usage_log.total_cost_usd
                logger.debug(
                    f"[ClaudeCodeWidget] Logged usage: ${mutation.usage_log.total_cost_usd:.4f}, "
                    f"total: ${self.total_cost_usd:.4f}"
                )

    # ========================================================================
    # Blueprint Serialization
    # ========================================================================

    def _serialize_config(self) -> dict:
        """Serialize widget configuration to dict.

        Returns:
            Config dict with all widget parameters and state
        """
        return {
            # Core config (v1.0)
            "cwd": self.cwd,
            "shared_instance": self.shared_instance,
            "resume_id": self.resume_id,  # State
            # Tool permissions (v1.1)
            "allowed_tools": self.allowed_tools,
            "disallowed_tools": self.disallowed_tools,
            # Bash safety (v1.1)
            "bash_allow_patterns": self.bash_allow_patterns,
            "bash_block_patterns": self.bash_block_patterns,
            "bash_dry_run_patterns": self.bash_dry_run_patterns,
            # Budget controls (v1.1)
            "max_budget_usd": self.max_budget_usd,
            "max_turns": self.max_turns,
            # State (v1.1)
            "total_cost_usd": self.total_cost_usd,
            "usage_logs": [asdict(log) for log in self.usage_logs],
            # Observability (v1.1) - note: hooks are not serializable, must be re-added
            "usage_log_file": str(self.usage_log_file),
        }

    # Note: to_blueprint_config() inherited from BasePlugin

    @classmethod
    def from_blueprint_config(cls, config: ComponentConfig, agent: "Agent") -> "ClaudeCodeWidget":
        """Deserialize widget from blueprint config.

        Supports both v1.0 and v1.1 config formats for backward compatibility.

        Args:
            config: Component configuration
            agent: Agent instance (for context)

        Returns:
            ClaudeCodeWidget instance
        """
        widget_config = config.config or {}
        cwd = widget_config.get("cwd")
        if not cwd:
            raise ValueError("ClaudeCodeWidget requires 'cwd' in config")

        # v1.0 parameters
        shared_instance = widget_config.get("shared_instance", False)
        resume_id = widget_config.get("resume_id")

        # v1.1 parameters (with defaults for backward compatibility)
        allowed_tools = widget_config.get("allowed_tools")
        disallowed_tools = widget_config.get("disallowed_tools")
        bash_allow_patterns = widget_config.get("bash_allow_patterns")
        bash_block_patterns = widget_config.get("bash_block_patterns")
        bash_dry_run_patterns = widget_config.get("bash_dry_run_patterns")
        max_budget_usd = widget_config.get("max_budget_usd")
        max_turns = widget_config.get("max_turns", 10)
        usage_log_file = widget_config.get("usage_log_file")

        # Create widget with all parameters
        widget = cls(
            cwd=cwd,
            shared_instance=shared_instance,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
            bash_allow_patterns=bash_allow_patterns,
            bash_block_patterns=bash_block_patterns,
            bash_dry_run_patterns=bash_dry_run_patterns,
            max_budget_usd=max_budget_usd,
            max_turns=max_turns,
            usage_log_file=usage_log_file,
        )

        # Restore instance_id
        widget.instance_id = config.instance_id

        # Restore state
        widget.resume_id = resume_id
        widget.total_cost_usd = widget_config.get("total_cost_usd", 0.0)

        # Restore usage logs
        usage_logs_data = widget_config.get("usage_logs", [])
        widget.usage_logs = [UsageLog(**log_dict) for log_dict in usage_logs_data]

        return widget
