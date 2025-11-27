"""Session manager for CLI.

Coordinates between VSP consumer, ThreadProtocol builder, and persistence.
"""

import inspect
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from chimera_cli.config import CLIConfig
from chimera_cli.core.blueprint import BlueprintManager
from chimera_cli.core.thread_protocol import ThreadPersistence, ThreadProtocolBuilder
from chimera_cli.core.vsp_consumer import StreamProcessor, VSPStreamConsumer


class ChatSession:
    """Manages a single chat session."""

    def __init__(
        self,
        config: CLIConfig,
        blueprint_manager: BlueprintManager,
        thread_persistence: ThreadPersistence,
        thread_id: Optional[str] = None,
        blueprint_data: Optional[Dict[str, Any]] = None,
    ):
        """Initialize session.

        Args:
            config: CLI configuration
            blueprint_manager: Blueprint manager instance
            thread_persistence: Thread persistence instance
            thread_id: Optional thread ID (for resuming)
            blueprint_data: Optional blueprint data (for new threads)
        """
        self.config = config
        self.blueprint_manager = blueprint_manager
        self.thread_persistence = thread_persistence
        self.thread_id = thread_id or str(uuid4())
        self.blueprint_data = blueprint_data

        # Initialize ThreadProtocol builder
        # Determine persist path for incremental writes
        thread_filepath = thread_persistence.base_path / f"{self.thread_id}.jsonl"

        if blueprint_data:
            # New session - enable incremental writes from the start
            blueprint_event = blueprint_manager.create_thread_blueprint_event(
                blueprint_data, self.thread_id
            )
            self.builder = ThreadProtocolBuilder(blueprint_event, persist_path=thread_filepath)
        else:
            # Resumed session - load from disk WITHOUT incremental writes
            # (to avoid duplicating events that are already on disk)
            events = thread_persistence.load_thread(self.thread_id)
            if not events:
                raise ValueError(f"Thread {self.thread_id} not found")

            # First event is blueprint
            self.builder = ThreadProtocolBuilder(events[0])
            # Add remaining events (without writing to disk)
            for event in events[1:]:
                self.builder.add_event(event)

            # NOW enable incremental writes for future events
            self.builder.persist_path = thread_filepath

        # Create VSP consumer
        self.consumer = VSPStreamConsumer(config.server_url)

        # Create stream processor
        self.processor = StreamProcessor(self.builder)

    async def send_message(
        self,
        message: str,
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_thinking_delta: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_claude_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_approval_request: Optional[Callable[[list], Dict[str, Any]]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ):
        """Send a message and process response.

        Args:
            message: User message content
            on_text_delta: Callback for text deltas
            on_thinking_delta: Callback for thinking deltas
            on_tool_call: Callback for tool calls
            on_tool_result: Callback for tool results
            on_claude_event: Callback for Claude Code events (data-app-claude)
            on_approval_request: Callback for tool approval requests
                               Takes list of pending tool dicts, returns approvals dict
            on_error: Callback for error events (errorText: str)
        """
        # Get current thread protocol as event array
        # Server will emit user turn events (user-turn-start, user-message, user-turn-end)
        # which we'll receive via SSE and add to our local ThreadProtocol
        thread_protocol = self.builder.get_events()

        # Stream response
        async with self.consumer:
            stream = self.consumer.send_user_message(
                message, thread_protocol, client_context=client_context
            )

            await self.processor.process_stream(
                stream,
                on_text_delta=on_text_delta,
                on_thinking_delta=on_thinking_delta,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
                on_claude_event=on_claude_event,
                on_error=on_error,
            )

            # Check if there are deferred tools awaiting approval
            if self.processor.has_deferred_tools():
                # Consume (get and clear) pending tools to prevent re-prompting
                # Tools transition from "pending execution" to "awaiting approval"
                pending_tools = self.builder.consume_pending_tools()

                if pending_tools and on_approval_request:
                    # Get approval decisions from user
                    approvals = on_approval_request(pending_tools)

                    # Support async callbacks (for Textual)
                    import inspect

                    if inspect.isawaitable(approvals):
                        approvals = await approvals

                    if approvals:
                        # Resume with approvals
                        await self._send_approvals(
                            approvals,
                            on_text_delta=on_text_delta,
                            on_thinking_delta=on_thinking_delta,
                            on_tool_call=on_tool_call,
                            on_tool_result=on_tool_result,
                            on_claude_event=on_claude_event,
                            on_approval_request=on_approval_request,
                            on_error=on_error,
                            client_context=client_context,
                        )

        # Auto-save if enabled
        if self.config.auto_save:
            self.save()

    async def _send_approvals(
        self,
        approvals: Dict[str, Any],
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_thinking_delta: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_tool_result: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_claude_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_approval_request: Optional[Callable[[list], Dict[str, Any]]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ):
        """Send tool approvals and resume agent execution.

        Args:
            approvals: Dict mapping tool_call_id to approval decision
            on_text_delta: Callback for text deltas
            on_thinking_delta: Callback for thinking deltas
            on_tool_call: Callback for tool calls
            on_tool_result: Callback for tool results
            on_claude_event: Callback for Claude Code events (data-app-claude)
            on_approval_request: Callback for nested approval requests
            on_error: Callback for error events
        """
        # Get current thread protocol
        thread_protocol = self.builder.get_events()

        # Stream response with approvals
        stream = self.consumer.send_deferred_approvals(
            approvals, thread_protocol, client_context=client_context
        )

        await self.processor.process_stream(
            stream,
            on_text_delta=on_text_delta,
            on_thinking_delta=on_thinking_delta,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
            on_claude_event=on_claude_event,
            on_error=on_error,
        )

        # Check for nested deferred tools (tools that need approval after previous approvals)
        if self.processor.has_deferred_tools():
            # Consume (get and clear) pending tools to prevent re-prompting
            pending_tools = self.builder.consume_pending_tools()

            if pending_tools and on_approval_request:
                # Recursively handle nested approvals
                nested_approvals = on_approval_request(pending_tools)

                if inspect.isawaitable(nested_approvals):
                    nested_approvals = await nested_approvals

                    if nested_approvals:
                        await self._send_approvals(
                            nested_approvals,
                            on_text_delta=on_text_delta,
                            on_thinking_delta=on_thinking_delta,
                            on_tool_call=on_tool_call,
                            on_tool_result=on_tool_result,
                            on_claude_event=on_claude_event,
                            on_approval_request=on_approval_request,
                            on_error=on_error,
                            client_context=client_context,
                        )

    def save(self):
        """Save current thread to disk."""
        jsonl = self.builder.to_jsonl()
        self.thread_persistence.save_thread(self.thread_id, jsonl)

        # Update last_thread_id in config after successful save
        self.config.last_thread_id = self.thread_id

    def get_thread_jsonl(self) -> str:
        """Get current thread as JSONL.

        Returns:
            ThreadProtocol JSONL string
        """
        return self.builder.to_jsonl()

    def get_events(self):
        """Get all thread events.

        Returns:
            List of event dicts
        """
        return self.builder.get_events()


class SessionManager:
    """Manages chat sessions for CLI."""

    def __init__(self, cli_dir: Path, blueprints_dir: Path):
        """Initialize session manager.

        Args:
            cli_dir: CLI directory (contains config.json and thread_history/)
            blueprints_dir: Directory containing blueprint JSON files
        """
        self.cli_dir = Path(cli_dir)
        self.blueprints_dir = Path(blueprints_dir)

        # Initialize components
        self.config = CLIConfig(self.cli_dir / "config.json")
        self.blueprint_manager = BlueprintManager(self.blueprints_dir)
        self.thread_persistence = ThreadPersistence(self.cli_dir / "thread_history")

        # Current session
        self.current_session: Optional[ChatSession] = None

    def start_new_session(self, blueprint_data: Dict[str, Any]) -> ChatSession:
        """Start a new chat session with blueprint.

        Args:
            blueprint_data: Blueprint data dict

        Returns:
            New ChatSession instance
        """
        thread_id = str(uuid4())

        self.current_session = ChatSession(
            self.config,
            self.blueprint_manager,
            self.thread_persistence,
            thread_id=thread_id,
            blueprint_data=blueprint_data,
        )

        # Don't set last_thread_id yet - wait until first save
        # It will be set in ChatSession.save()

        return self.current_session

    def resume_session(self, thread_id: str) -> ChatSession:
        """Resume an existing chat session.

        Args:
            thread_id: Thread ID to resume

        Returns:
            Resumed ChatSession instance
        """
        self.current_session = ChatSession(
            self.config, self.blueprint_manager, self.thread_persistence, thread_id=thread_id
        )

        # Update config
        self.config.last_thread_id = thread_id

        return self.current_session

    def list_threads(self):
        """List all saved threads.

        Returns:
            List of thread metadata dicts
        """
        return self.thread_persistence.list_threads()

    def list_blueprints(self):
        """List all available blueprints.

        Returns:
            List of blueprint metadata dicts
        """
        return self.blueprint_manager.list_blueprints()

    def get_last_used_blueprint(self) -> Optional[Dict[str, Any]]:
        """Get the last used blueprint.

        Returns:
            Blueprint data dict or None
        """
        last_path = self.config.last_blueprint_path
        if last_path:
            return self.blueprint_manager.load_blueprint(last_path)

        return self.blueprint_manager.get_default_blueprint()
