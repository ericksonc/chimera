"""
Agent representation for the Chimera MAS.

This module defines the Agent class that both holds configuration
and provides Pydantic AI integration for running agents.

The Agent is the point-of-view for inference - each agent builds its own
view of the world rather than having a central orchestrator compose context.
"""

import asyncio
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

import logfire
import yaml
from pydantic_ai import Agent as PAIAgent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.output import DeferredToolRequests
from pydantic_ai.run import AgentRunResult
from pydantic_graph.beta import StepContext

# from .exceptions import ConfigurationError, AgentNotConfiguredError # TODO: custom exception types?
from .models import create_model

# Configure logger
logger = logging.getLogger(__name__)


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID with optional prefix.

    Args:
        prefix: Optional prefix (e.g., "appr-" for approval IDs)

    Returns:
        Random hex string with prefix
    """
    random_part = secrets.token_hex(6)  # 12 characters
    return f"{prefix}{random_part}" if prefix else random_part


from .protocols import ReadableThreadState  # noqa: E402
from .protocols.transformer import ThreadProtocolTransformer  # noqa: E402
from .thread import ThreadDeps  # noqa: E402
from .types import UserInput, UserInputDeferredTools, UserInputMessage  # noqa: E402

if TYPE_CHECKING:
    from .threadprotocol.blueprint import InlineAgentConfig
    from .widget import Widget

logfire.configure()
# logfire.configure(send_to_logfire="if-token-present")

logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)


@dataclass
class PAIDeps:
    """Focused deps interface for PAI tools.

    Decouples agent dependencies from the thread graph dependencies.
    """

    client_context: Dict[str, Any]  # cwd, model override, any future client_context data
    emit_threadprotocol_event: Callable  # For mutations
    emit_vsp_event: Callable  # For streaming events
    thread_id: UUID  # For feedback/logging
    active_agent: Optional[str]  # For context


class Agent:
    """Agent configuration and runtime functionality.

    The Agent is the point-of-view for inference. Each agent builds its own
    view of the world (message history, widgets, tools, context) rather than
    having a central orchestrator compose it.

    Agents can be loaded from YAML registry files or created programmatically.
    They serialize to BlueprintProtocol for Turn 0 configuration.
    """

    def __init__(
        self,
        id: str,
        name: str,
        base_prompt: str,
        description: str = "",
        identifier: Optional[str] = None,
        model_string: Optional[str] = None,
        widgets: Optional[List["Widget"]] = None,
        metadata: Optional[dict] = None,
    ):
        """Initialize Agent with configuration.

        Args:
            id: Agent UUID (string)
            name: Human-readable name
            base_prompt: Core instructions/persona
            description: How this agent is seen by others
            identifier: Thread-scoped identifier (defaults to name if not provided)
            model_string: Optional model override (e.g., "openai:gpt-4o")
            widgets: Agent-level widgets (private to this agent)
            metadata: Optional metadata (e.g., voice_id, custom fields)
        """
        self.id = id
        self.name = name
        self.base_prompt = base_prompt
        self.description = description
        self.identifier = identifier if identifier is not None else name
        self.model_string = model_string
        self.widgets: List["Widget"] = widgets or []
        self.metadata = metadata or {}

    @classmethod
    def from_yaml(cls, path: str) -> "Agent":
        """Load agent from YAML registry file.

        Args:
            path: Path to YAML file (e.g., "agents/jarvis.yaml")

        Returns:
            Agent instance

        Raises:
            FileNotFoundError: If YAML file doesn't exist
            ValueError: If YAML is invalid or missing required fields
        """
        yaml_path = Path(path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Agent YAML not found: {path}")

        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        # Required field
        if "prompt" not in data:
            raise ValueError(f"Agent YAML missing required 'prompt' field: {path}")

        # Extract metadata (custom fields beyond core config)
        metadata = {}
        core_fields = {"id", "name", "identifier", "description", "prompt", "model", "model_string"}
        for key, value in data.items():
            if key not in core_fields:
                metadata[key] = value

        return cls(
            id=data.get("id", str(uuid4())),
            name=data.get("name", "Agent"),
            base_prompt=data["prompt"],
            description=data.get("description", ""),
            identifier=data.get("identifier"),  # Defaults to name if None
            model_string=data.get("model")
            or data.get("model_string"),  # Support both 'model' and 'model_string'
            metadata=metadata,
        )

    def register_widget(self, widget: "Widget") -> None:
        """Register a widget with this agent (agent-level, private).

        Args:
            widget: Widget instance to register
        """
        if widget not in self.widgets:
            widget._agent = self
            self.widgets.append(widget)

    def register_widgets(self, widgets: List["Widget"]) -> None:
        """Register multiple widgets with this agent.

        Sets the agent reference on each widget and adds them to the widgets list.

        Args:
            widgets: List of Widget instances to register
        """
        for widget in widgets:
            widget._agent = self
        self.widgets = widgets

    def to_blueprint_config(self) -> "InlineAgentConfig":
        """Serialize agent to BlueprintProtocol format.

        Returns:
            InlineAgentConfig for BlueprintProtocol
        """
        from .threadprotocol.blueprint import InlineAgentConfig

        # Serialize widgets
        widget_configs = [w.to_blueprint_config() for w in self.widgets]

        # v0.0.7: id IS the identifier (no separate identifier field in blueprint)
        return InlineAgentConfig(
            id=self.id,
            name=self.name,
            description=self.description,
            base_prompt=self.base_prompt,
            model_string=self.model_string,
            widgets=widget_configs,
            metadata=self.metadata,
        )

    @classmethod
    def from_blueprint_config(cls, config: "InlineAgentConfig") -> "Agent":
        """Deserialize agent from BlueprintProtocol format.

        Args:
            config: InlineAgentConfig from Blueprint

        Returns:
            Agent instance with hydrated widgets
        """
        from .widget_registry import hydrate_widget

        # Create agent first (with empty widgets list)
        # In v0.0.7, config.id IS the identifier (no separate identifier field)
        agent = cls(
            id=config.id,
            name=config.name,
            description=config.description,
            base_prompt=config.base_prompt,
            identifier=config.id,  # v0.0.7: id IS the identifier
            model_string=config.model_string,
            widgets=[],  # Empty for now
            metadata=config.metadata,
        )

        # Now hydrate widgets, passing the agent for context
        widgets = [hydrate_widget(widget_config, agent) for widget_config in config.widgets]

        # Register widgets (sets _agent on each widget)
        agent.register_widgets(widgets)

        return agent

    async def run_stream(
        self,
        ctx: StepContext[ReadableThreadState, ThreadDeps, None],  # type: ignore[type-arg]
        transformer: ThreadProtocolTransformer,
        message: str,
        user_input: UserInput | None = None,
    ) -> AgentRunResult:
        """Run the agent with streaming and return the final result.

        This is the main entry point called by ActiveSpace. It:
        1. Emits data-agent-start boundary event (v0.0.7)
        2. Sets up the PAI agent with model, prompts, and instructions
        3. Transforms ThreadProtocol history to ModelMessages
        4. Builds DeferredToolResults if resuming from approval
        5. Runs agent.iter() with the user message and streaming
        6. Emits both ThreadProtocol and VSP events
        7. Emits data-agent-finish boundary event (v0.0.7)
        8. Returns the final AgentRunResult

        Args:
            ctx: Step context with state (ReadableThreadState) and deps (ThreadDeps)
            transformer: Transformer for converting ThreadProtocol to ModelMessages
            message: The message to process (user input or previous agent response)
            user_input: Typed user input (UserInputMessage | UserInputDeferredTools)

        Returns:
            AgentRunResult from Pydantic AI
        """
        print(f"\n{'=' * 80}")
        print(f"[AGENT RUN] Running turn for: {self.name}")
        print(f"[AGENT RUN] Agent ID: {self.id}")
        print(f"[AGENT RUN] Message: {message[:100]}...")
        print(f"{'=' * 80}\n")

        # Generate message ID for this response (used throughout the turn)
        message_id = f"msg_{uuid4().hex}"

        # Write data-agent-start event (ThreadProtocol v0.0.7 - custom VSP event)
        if ctx.deps.thread_writer:  # type: ignore[attr-defined]
            await ctx.deps.thread_writer.write_turn_boundary(  # type: ignore[attr-defined]
                "data-agent-start",
                data={"agentId": str(self.id), "agentName": self.name, "messageId": message_id},
            )

        # Emit VSP event for data-agent-start (boundary event - includes threadId)
        await ctx.deps.emit_vsp_event(  # type: ignore[attr-defined]
            {
                "type": "data-agent-start",
                "data": {"agentId": str(self.id), "agentName": self.name, "messageId": message_id},
            }
        )

        # Setup PAI agent and get message history + ambient instructions
        pai_agent, message_history, ambient_instructions = await self._setup_pai_agent(
            ctx, transformer, user_input
        )

        # Run the agent turn using Pydantic AI's agent.iter()
        result = await self._run_pai_agent(
            pai_agent,
            message_history,
            message,
            ctx,
            transformer,
            user_input,
            message_id,
            ambient_instructions,
        )

        # Write data-agent-finish event (ThreadProtocol v0.0.7 - custom VSP event)
        # Note: completionStatus removed in v0.0.7, can be inferred from events
        if ctx.deps.thread_writer:  # type: ignore[attr-defined]
            await ctx.deps.thread_writer.write_turn_boundary(  # type: ignore[attr-defined]
                "data-agent-finish",
                data={"agentId": str(self.id), "agentName": self.name, "messageId": message_id},
            )

        # Emit VSP event for data-agent-finish (boundary event - includes threadId)
        await ctx.deps.emit_vsp_event(  # type: ignore[attr-defined]
            {
                "type": "data-agent-finish",
                "data": {"agentId": str(self.id), "agentName": self.name, "messageId": message_id},
            }
        )

        return result

    async def _setup_pai_agent(
        self,
        ctx: StepContext[ReadableThreadState, ThreadDeps, None],  # type: ignore[type-arg]
        transformer: ThreadProtocolTransformer,
        user_input: UserInput | None = None,
    ) -> tuple[PAIAgent, list[ModelMessage], list[str]]:
        """Setup PAI agent with model, prompts, and message history.

        NEW ARCHITECTURE (2025-11-11):
        - ONLY agent base_prompt goes to PAI's instructions (system prompt)
        - Dynamic instructions collected but returned separately for user message enhancement
        - Clear separation: persona in system, context in user message

        Args:
            ctx: Step context with state and deps
            transformer: Transformer for ThreadProtocol → ModelMessages
            user_input: Typed user input (UserInputMessage | UserInputDeferredTools)

        Returns:
            Tuple of (pai_agent, message_history, ambient_instructions)
        """
        # Model precedence: client_context.model > agent.model_string > DEFAULT_MODEL_STRING
        client_context = ctx.deps.client_context or {}  # type: ignore[attr-defined]
        client_model_override = client_context.get("model")
        model_string = (
            client_model_override
            or self.model_string
            or os.getenv("DEFAULT_MODEL_STRING", "openai:gpt-4o")
        )
        # At this point model_string is guaranteed str due to getenv default
        model = create_model(str(model_string))

        if client_model_override:
            print(f"[AGENT SETUP] Using client model override: {client_model_override}")

        # Collect dynamic instructions from all plugins (space + space widgets + agent widgets)
        # Space aggregates and filters to only those that implement get_instructions
        ambient_instructions: List[str] = []
        instruction_providers = ctx.state.active_space.get_instructions_providers()  # type: ignore[attr-defined]
        print(f"[AGENT SETUP] Found {len(instruction_providers)} instruction providers")
        for provider in instruction_providers:
            plugin_instructions = await provider(ctx)  # Pass full ctx for deps access
            if plugin_instructions:
                print(f"[AGENT SETUP] Provider gave instructions: {plugin_instructions[:100]}...")
                ambient_instructions.append(plugin_instructions)

        print(f"[AGENT SETUP] Total ambient instructions collected: {len(ambient_instructions)}")

        # NEW ARCHITECTURE: Only base_prompt goes to PAI instructions
        # Dynamic instructions will be injected into the user message instead
        print("[AGENT SETUP] ARCHITECTURE: System prompt = base_prompt ONLY")
        print("[AGENT SETUP] ARCHITECTURE: Ambient instructions = user message enhancement")

        # Collect toolsets from all plugins (space + space widgets + agent widgets)
        # Space aggregates and filters to only those that implement get_toolset
        toolsets = []
        toolset_providers = ctx.state.active_space.get_toolset_providers()  # type: ignore[attr-defined]
        for provider in toolset_providers:
            toolset = provider(ctx)  # Pass ctx so plugins can access deps
            if toolset:
                toolsets.append(toolset)

        # Create PAI agent fresh for this turn with toolsets
        print("[AGENT SETUP] Creating PAI agent with:")
        print("  - instructions: ONLY base_prompt (persona)")
        print(f"    [PERSONA]: {self.base_prompt[:80]}...")
        print(
            f"  - ambient_instructions: {len(ambient_instructions)} items (will go in user message)"
        )
        for i, instr in enumerate(ambient_instructions):
            print(f"    [AMBIENT[{i}]]: {instr[:80]}...")
        print(f"  - toolsets: {len(toolsets)} items")

        print(transformer.__class__)

        # OLD ARCHITECTURE (kept for easy rollback):
        # all_instructions = [self.base_prompt] + ambient_instructions
        # pai_agent = PAIAgent(
        #     model=model,
        #     instructions=all_instructions,  # Everything in system
        #     deps_type=type(ctx),
        #     toolsets=toolsets,
        #     model_settings={'temperature': 1.0}
        # )

        # NEW ARCHITECTURE (2025-11-11): Only base_prompt in system
        pai_agent = PAIAgent(
            model=model,
            instructions=[self.base_prompt],  # ONLY persona - no dynamic instructions
            deps_type=PAIDeps,
            toolsets=toolsets,  # Pass toolsets at construction
            model_settings={"temperature": 1.0},
        )

        # Get ThreadProtocol events and transform to ModelMessages
        threadprotocol_events = ctx.state.get_threadprotocol_events()  # type: ignore[attr-defined]
        print(f"[AGENT SETUP] Got {len(threadprotocol_events)} ThreadProtocol events")

        # Transform to ModelMessages
        # Note: agent_id is ignored by GenericTransformer, only used by MultiAgentTransformer
        message_history = transformer.transform(
            events=threadprotocol_events,
            agent_id=None,  # Agent IDs are strings, not UUIDs; pass None for now
        )

        print(f"[AGENT SETUP] Transformed to {len(message_history)} ModelMessages")
        for i, msg in enumerate(message_history[:3]):  # Show first 3
            print(f"  [{i}] {type(msg).__name__}: {str(msg)[:100]}...")

        return (pai_agent, message_history, ambient_instructions)  # type: ignore[return-value]

    async def _run_pai_agent(
        self,
        pai_agent: PAIAgent,
        message_history: List[ModelMessage],
        message: str,
        ctx: StepContext[ReadableThreadState, ThreadDeps, None],  # type: ignore[type-arg]
        transformer: ThreadProtocolTransformer,
        user_input: UserInput | None = None,
        message_id: str | None = None,
        ambient_instructions: List[str] | None = None,
    ) -> AgentRunResult:
        """Run the PAI agent using agent.iter() with hook-based streaming.

        This uses the ChimeraVSPEventStream pattern to transform Pydantic AI
        events into VSP events with ThreadProtocol persistence.

        The hook-based pattern decomposes event generation into specialized
        lifecycle hooks (before_stream, handle_text_delta, etc.) rather than
        inline logic, making it easier to extend and test.

        NEW ARCHITECTURE (2025-11-11):
        - Enhances user message with ambient instructions using clear demarcation
        - Agent receives explicit framing: what's context vs. what user typed

        Args:
            pai_agent: Fresh PAIAgent instance configured for this turn
            message_history: ModelMessages transformed from ThreadProtocol
            message: The user message to process
            ctx: Step context with state and deps
            transformer: Transformer for building deferred tool results
            user_input: Typed user input (UserInputMessage | UserInputDeferredTools)
            message_id: Message ID for this response (generated by run_stream)
            ambient_instructions: Dynamic instructions from widgets/spaces for user message

        Returns:
            AgentRunResult from Pydantic AI
        """
        from chimera_core.prompting import build_enhanced_user_message
        from chimera_core.ui import (
            ThreadProtocolPersistenceWrapper,
            VSPEventStream,
            emit_tool_approval_request,
            emit_tool_output_denied,
        )

        # Get emit methods from deps (injected infrastructure)
        emit_threadprotocol_event = ctx.deps.emit_threadprotocol_event  # type: ignore[attr-defined]
        emit_vsp_event = ctx.deps.emit_vsp_event  # type: ignore[attr-defined]

        # Use provided message_id (generated in run_stream for consistency)
        if message_id is None:
            message_id = f"msg_{uuid4().hex}"

        # Build deferred tool results if resuming from approval
        threadprotocol_events = ctx.state.get_threadprotocol_events()  # type: ignore[attr-defined]
        deferred_results = transformer.build_deferred_tool_results(
            threadprotocol_events, user_input
        )

        if deferred_results:
            print("[AGENT RUN] Resuming with deferred tool results:")
            print(f"  - Approvals: {len(deferred_results.approvals)}")
            print(f"  - External calls: {len(deferred_results.calls)}")

            # VSP v6: Emit tool-output-denied for denied tools
            if user_input and isinstance(user_input, UserInputDeferredTools):
                approvals = user_input.approvals
                for tool_call_id, decision in approvals.items():
                    # Check if tool was denied
                    is_denied = False
                    if isinstance(decision, bool) and decision is False:
                        is_denied = True
                    elif isinstance(decision, dict) and decision.get("approved") is False:
                        is_denied = True

                    if is_denied:
                        # Use helper function for dual emission
                        await emit_tool_output_denied(
                            tool_call_id,
                            emit_threadprotocol=emit_threadprotocol_event,
                            emit_vsp=emit_vsp_event,
                        )
                        print(f"[AGENT RUN] Emitted tool-output-denied: toolCallId={tool_call_id}")

        # Get thread ID for VSP events
        # Use canonical thread_id from ReadableThreadState
        thread_id = ctx.state.thread_id  # type: ignore[attr-defined]
        thread_id_str = str(thread_id)

        # Create VSP event stream with ThreadProtocol persistence wrapper
        # This separates concerns: VSP generation vs. storage
        vsp_stream = VSPEventStream(
            message_id=message_id, thread_id=thread_id_str, include_thread_id=True
        )
        event_stream = ThreadProtocolPersistenceWrapper(
            wrapped_stream=vsp_stream, emit_threadprotocol=emit_threadprotocol_event
        )

        # Get output_type from the active space
        # Space controls what output types are allowed (default: str)
        space_output_type = ctx.state.active_space.output_type  # type: ignore[attr-defined]

        # Always include DeferredToolRequests for tool approval flow
        # Convert to list if needed, ensure DeferredToolRequests is included
        if isinstance(space_output_type, list):
            output_type = list(space_output_type)  # Copy to avoid mutating space's list
            if DeferredToolRequests not in output_type:
                output_type.append(DeferredToolRequests)
        else:
            output_type = [space_output_type, DeferredToolRequests]

        # Construct PAIDeps for the agent
        # This decouples agent dependencies from the thread graph dependencies
        pai_deps = PAIDeps(
            client_context=ctx.deps.client_context or {},  # type: ignore[attr-defined]
            emit_threadprotocol_event=ctx.deps.emit_threadprotocol_event,  # type: ignore[attr-defined]
            emit_vsp_event=ctx.deps.emit_vsp_event,  # type: ignore[attr-defined]
            thread_id=thread_id,
            active_agent=self.id,
        )

        # Use agent.iter() to run through the execution graph
        # When resuming with deferred tools, DON'T pass a message (PAI pattern)
        # Only new user messages should be passed as positional arg
        if deferred_results:
            # Resuming from deferred tools - no new message
            print(f"\n{'=' * 80}")
            print(f"[DEFERRED RESUMPTION] message_history has {len(message_history)} messages:")
            for i, msg in enumerate(message_history):
                print(f"\n  Message {i}: {type(msg).__name__}")
                print(f"    Parts: {len(msg.parts)}")
                for j, part in enumerate(msg.parts):
                    print(f"      Part {j}: {type(part).__name__}")
                    if hasattr(part, "tool_name"):
                        print(f"        tool_name: {part.tool_name}")
                    if hasattr(part, "tool_call_id"):
                        print(f"        tool_call_id: {part.tool_call_id}")
                    if hasattr(part, "content"):
                        content_preview = str(part.content)[:100]
                        print(f"        content: {content_preview}")
            print(f"{'=' * 80}\n")

            agent_iter = pai_agent.iter(  # type: ignore[call-overload]
                message_history=message_history,
                deferred_tool_results=deferred_results,
                output_type=output_type,
                deps=pai_deps,
            )
        else:
            # Normal flow - new user message
            # Extract attachments from UserInputMessage for multimodal support
            attachments = None
            if isinstance(user_input, UserInputMessage) and user_input.attachments:
                attachments = user_input.attachments
                print(f"[AGENT RUN] Found {len(attachments)} attachments")
                for i, att in enumerate(attachments):
                    print(f"  [{i}] {att.media_type}: {att.filename or 'unnamed'}")

            # NEW ARCHITECTURE: Enhance message with ambient instructions and attachments
            enhanced_message = build_enhanced_user_message(
                user_input=message,
                ambient_instructions=ambient_instructions,
                attachments=attachments,
            )

            # Log message preview (handle both str and list return types)
            if isinstance(enhanced_message, str):
                print("[AGENT RUN] Enhanced message preview:")
                print(f"{enhanced_message[:200]}...")
            else:
                print("[AGENT RUN] Enhanced multimodal message:")
                print(f"  Text: {str(enhanced_message[0])[:200]}...")
                print(f"  Attachments: {len(enhanced_message) - 1}")

            agent_iter = pai_agent.iter(  # type: ignore[call-overload]
                enhanced_message,  # Enhanced message with ambient context and attachments
                message_history=message_history,
                deferred_tool_results=None,  # Explicit None for clarity
                output_type=output_type,
                deps=pai_deps,
            )

        # Transform Pydantic AI events to VSP events using hook-based streaming
        try:
            async with agent_iter as agent_run:
                # Stream events using hook-based pattern
                async for vsp_event in event_stream.transform_pai_stream(agent_run):
                    # Emit VSP event to client (SSE)
                    # Delta events don't include threadId (only boundary events do)
                    include_thread_id = vsp_event.get("type") not in [
                        "text-delta",
                        "tool-input-delta",
                        "reasoning-delta",
                    ]
                    await emit_vsp_event(vsp_event, include_thread_id=include_thread_id)

                # Get the final result
                result = agent_run.result
        except asyncio.CancelledError:
            # User cancelled execution (halt button) - log and re-raise
            logger.warning(f"[AGENT {self.name}] Execution cancelled by user")
            raise

        # Check if we got DeferredToolRequests
        if isinstance(result.output, DeferredToolRequests):
            print("[AGENT RUN] Agent run ended with DeferredToolRequests:")
            print(f"  - Approvals needed: {len(result.output.approvals)}")
            print(f"  - External calls: {len(result.output.calls)}")

            # VSP v6: Emit tool-approval-request events for each deferred tool
            # approvals is a list[ToolCallPart], not a dict
            for approval in result.output.approvals:
                tool_call_id = approval.tool_call_id
                approval_id = generate_id("appr-")

                # Use helper function for dual emission
                await emit_tool_approval_request(
                    approval_id,
                    tool_call_id,
                    emit_threadprotocol=emit_threadprotocol_event,
                    emit_vsp=emit_vsp_event,
                )

                print(
                    f"[AGENT RUN] Emitted tool-approval-request: approvalId={approval_id}, toolCallId={tool_call_id}"
                )

        # Note: finish/finish-step events are now handled by ChimeraVSPEventStream.after_stream()
        # No need to emit them manually here

        # Return the final result
        return result  # type: ignore[no-any-return]
