"""
Agent representation for the Chimera MAS.

This module defines the Agent class that both holds configuration
and provides Pydantic AI integration for running agents.

The Agent is the point-of-view for inference - each agent builds its own
view of the world rather than having a central orchestrator compose context.
"""

from typing import List, TYPE_CHECKING, Optional
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
import os
import yaml

from pydantic_ai import Agent as PAIAgent
from pydantic_ai.messages import (
    ModelMessage,
    PartStartEvent,
    PartDeltaEvent,
    FinalResultEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    FunctionToolCallEvent,
    FunctionToolResultEvent
)
from pydantic_ai.run import AgentRunResult
from pydantic_graph.beta import StepContext

import logfire

# from .exceptions import ConfigurationError, AgentNotConfiguredError # TODO: custom exception types?
from .models import create_model

from .protocols import ReadableThreadState
from .protocols.transformer import ThreadProtocolTransformer
from .thread import ThreadDeps

if TYPE_CHECKING:
    from .widget import Widget
    from .threadprotocol.blueprint import InlineAgentConfig

logfire.configure(send_to_logfire='if-token-present')
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)


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
        model_string: Optional[str] = None,
        widgets: Optional[List["Widget"]] = None,
        metadata: Optional[dict] = None
    ):
        """Initialize Agent with configuration.

        Args:
            id: Agent UUID (string)
            name: Human-readable name
            base_prompt: Core instructions/persona
            description: How this agent is seen by others
            model_string: Optional model override (e.g., "openai:gpt-4o")
            widgets: Agent-level widgets (private to this agent)
            metadata: Optional metadata (e.g., voice_id, custom fields)
        """
        self.id = id
        self.name = name
        self.base_prompt = base_prompt
        self.description = description
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

        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)

        # Required field
        if 'prompt' not in data:
            raise ValueError(f"Agent YAML missing required 'prompt' field: {path}")

        # Extract metadata (custom fields beyond core config)
        metadata = {}
        core_fields = {'id', 'name', 'identifier', 'description', 'prompt', 'model_string'}
        for key, value in data.items():
            if key not in core_fields:
                metadata[key] = value

        return cls(
            id=data.get('id', str(uuid4())),
            name=data.get('name', 'Agent'),
            base_prompt=data['prompt'],
            description=data.get('description', ''),
            model_string=data.get('model_string'),
            metadata=metadata
        )

    def register_widget(self, widget: "Widget") -> None:
        """Register a widget with this agent (agent-level, private).

        Args:
            widget: Widget instance to register
        """
        if widget not in self.widgets:
            self.widgets.append(widget)

    def to_blueprint_config(self) -> "InlineAgentConfig":
        """Serialize agent to BlueprintProtocol format.

        Returns:
            InlineAgentConfig for BlueprintProtocol
        """
        from .threadprotocol.blueprint import InlineAgentConfig

        # Serialize widgets
        widget_configs = [w.to_blueprint_config() for w in self.widgets]

        return InlineAgentConfig(
            id=self.id,
            name=self.name,
            description=self.description,
            base_prompt=self.base_prompt,
            model_string=self.model_string,
            widgets=widget_configs
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

        # Hydrate widgets from ComponentConfigs
        widgets = [hydrate_widget(widget_config) for widget_config in config.widgets]

        return cls(
            id=config.id,
            name=config.name,
            description=config.description,
            base_prompt=config.base_prompt,
            model_string=config.model_string,
            widgets=widgets
        )


    async def run_stream(
        self,
        ctx: StepContext[ReadableThreadState, ThreadDeps, None],
        transformer: ThreadProtocolTransformer
    ) -> AgentRunResult:
        """Run the agent with streaming and return the final result.

        This is the main entry point called by ActiveSpace. It:
        1. Sets up the PAI agent with model, prompts, and instructions
        2. Transforms ThreadProtocol history to ModelMessages
        3. Runs agent.iter() with streaming
        4. Emits both ThreadProtocol and VSP events
        5. Returns the final AgentRunResult

        Args:
            ctx: Step context with state (ReadableThreadState) and deps (ThreadDeps)
            transformer: Transformer for converting ThreadProtocol to ModelMessages

        Returns:
            AgentRunResult from Pydantic AI
        """
        # Setup PAI agent and get message history
        pai_agent, message_history = self._setup_pai_agent(ctx, transformer)

        # Run the agent turn using Pydantic AI's agent.iter()
        result = await self._run_pai_agent(pai_agent, message_history, ctx)

        return result


    def _setup_pai_agent(
        self,
        ctx: StepContext[ReadableThreadState, ThreadDeps, None],
        transformer: ThreadProtocolTransformer
    ) -> tuple[PAIAgent, list[ModelMessage]]:
        """Setup PAI agent with model, prompts, and message history.

        Args:
            ctx: Step context with state and deps
            transformer: Transformer for ThreadProtocol → ModelMessages

        Returns:
            Tuple of (pai_agent, message_history)
        """
        # Model precedence: agent.model_string > DEFAULT_MODEL_STRING from env
        model_string = self.model_string or os.getenv("DEFAULT_MODEL_STRING", "openai:gpt-4o")
        model = create_model(model_string)

        # Collect dynamic instructions (ambient context from widgets, etc.)
        # TODO: Implement lifecycle hooks to collect instructions
        # For now, start with empty list
        instructions: List[str] = []

        # Create PAI agent fresh for this turn
        pai_agent = PAIAgent(
            model=model,
            system_prompt=self.base_prompt,  # Static agent identity
            instructions=instructions,  # Dynamic context (empty for now)
            deps_type=type(ctx)  # Pass ctx type for now
        )

        # TODO: Register widget tools with the PAI agent
        # for widget in self.widgets:
        #     for tool in widget.get_tools():
        #         pai_agent.tool(tool)

        # Get ThreadProtocol events and transform to ModelMessages
        # TODO: Access ThreadProtocol events from ctx.state
        # For now, start with empty history
        threadprotocol_events: list[dict] = []

        # Transform to ModelMessages
        message_history = transformer.transform(
            events=threadprotocol_events,
            agent_id=None  # Generic view for now
        )

        return (pai_agent, message_history)

    async def _run_pai_agent(
        self,
        pai_agent: PAIAgent,
        message_history: List[ModelMessage],
        ctx: StepContext[ReadableThreadState, ThreadDeps, None]
    ) -> AgentRunResult:
        """Run the PAI agent using agent.iter() with streaming.

        This implements the full streaming loop that:
        - Iterates through PAI's execution graph nodes
        - Streams text/thinking/tool deltas as they arrive
        - Emits ThreadProtocol events for persistence
        - Emits VSP events for client streaming
        - Returns the final AgentRunResult

        Args:
            pai_agent: Fresh PAIAgent instance configured for this turn
            message_history: ModelMessages transformed from ThreadProtocol
            ctx: Step context with state and deps

        Returns:
            AgentRunResult from Pydantic AI
        """
        # Get emit methods from deps (injected infrastructure)
        emit_threadprotocol_event = ctx.deps.emit_threadprotocol_event
        emit_vsp_event = ctx.deps.emit_vsp_event

        # Generate IDs for tracking parts
        message_id = f"msg_{uuid4().hex}"
        active_parts: dict[int, dict] = {}

        # Use agent.iter() to run through the execution graph
        async with pai_agent.iter(
            message_history=message_history,
            deps=ctx  # Pass full context as deps for now
        ) as agent_run:

            # Iterate through all execution nodes
            async for node in agent_run:

                # MODEL REQUEST NODE - Model is generating a response
                if PAIAgent.is_model_request_node(node):
                    async with node.stream(agent_run.ctx) as stream:
                        async for event in stream:

                            # New part starting (text, tool call, or thinking)
                            # TODO: look into how the distinction between "types of Part" actually happens in PAI
                            if isinstance(event, PartStartEvent):
                                idx = event.index
                                part = event.part

                                if isinstance(part, TextPart):
                                    # Text part starting
                                    part_id = f"{message_id}_text_{idx}"
                                    active_parts[idx] = {"id": part_id, "type": "text"}

                                    # Emit VSP text-start (boundary event, includes threadId)
                                    await emit_vsp_event({
                                        "type": "text-start",
                                        "id": part_id
                                    })

                                    # If initial content exists, emit it (delta, no threadId)
                                    if part.content:
                                        await emit_vsp_event({
                                            "type": "text-delta",
                                            "id": part_id,
                                            "delta": part.content
                                        }, include_thread_id=False)

                                elif isinstance(part, ToolCallPart):
                                    # Tool call starting
                                    tool_call_id = part.tool_call_id or f"call_{uuid4().hex}"
                                    active_parts[idx] = {
                                        "id": tool_call_id,
                                        "type": "tool",
                                        "name": part.tool_name
                                    }

                                    # Emit VSP tool-input-start (boundary event, includes threadId)
                                    await emit_vsp_event({
                                        "type": "tool-input-start",
                                        "toolCallId": tool_call_id,
                                        "toolName": part.tool_name
                                    })

                                elif isinstance(part, ThinkingPart):
                                    # Thinking/reasoning starting
                                    part_id = f"{message_id}_thinking_{idx}"
                                    active_parts[idx] = {"id": part_id, "type": "thinking"}

                                    # Emit VSP reasoning-start (boundary event, includes threadId)
                                    await emit_vsp_event({
                                        "type": "reasoning-start",
                                        "id": part_id
                                    })

                                    if part.content:
                                        # Emit delta (no threadId)
                                        await emit_vsp_event({
                                            "type": "reasoning-delta",
                                            "id": part_id,
                                            "delta": part.content
                                        }, include_thread_id=False)

                            # Incremental delta update to a part
                            elif isinstance(event, PartDeltaEvent):
                                idx = event.index
                                delta = event.delta

                                if idx not in active_parts:
                                    continue

                                part_info = active_parts[idx]

                                if isinstance(delta, TextPartDelta):
                                    # Text delta
                                    if delta.content_delta:
                                        await emit_vsp_event({
                                            "type": "text-delta",
                                            "id": part_info["id"],
                                            "delta": delta.content_delta
                                        }, include_thread_id=False)

                                elif isinstance(delta, ToolCallPartDelta):
                                    # Tool call args delta
                                    if delta.args_delta:
                                        args_str = delta.args_delta if isinstance(delta.args_delta, str) else str(delta.args_delta)
                                        await emit_vsp_event({
                                            "type": "tool-input-delta",
                                            "toolCallId": part_info["id"],
                                            "inputTextDelta": args_str
                                        }, include_thread_id=False)

                                elif isinstance(delta, ThinkingPartDelta):
                                    # Thinking delta
                                    if delta.content_delta:
                                        await emit_vsp_event({
                                            "type": "reasoning-delta",
                                            "id": part_info["id"],
                                            "delta": delta.content_delta
                                        }, include_thread_id=False)

                            # Final result available
                            elif isinstance(event, FinalResultEvent):
                                # Don't close parts yet - more deltas can come
                                pass

                        # After stream completes, close all active parts (end events are boundaries)
                        for idx, part_info in active_parts.items():
                            if part_info["type"] == "text":
                                await emit_vsp_event({
                                    "type": "text-end",
                                    "id": part_info["id"]
                                })
                            elif part_info["type"] == "thinking":
                                await emit_vsp_event({
                                    "type": "reasoning-end",
                                    "id": part_info["id"]
                                })

                        # Clear for next potential model request
                        active_parts.clear()

                # TOOL EXECUTION NODE - Tools are being called
                elif PAIAgent.is_call_tools_node(node):
                    async with node.stream(agent_run.ctx) as stream:
                        async for event in stream:

                            if isinstance(event, FunctionToolCallEvent):
                                # Tool is about to be called
                                tool_call_id = event.part.tool_call_id or f"call_{uuid4().hex}"

                                # Emit ThreadProtocol tool_call event
                                await emit_threadprotocol_event({
                                    "event_type": "tool_call",
                                    "agent_id": str(self.id),
                                    "tool_name": event.part.tool_name,
                                    "args": event.part.args,
                                    "tool_call_id": tool_call_id,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                })

                                # Emit VSP tool-input-available (boundary event, includes threadId)
                                await emit_vsp_event({
                                    "type": "tool-input-available",
                                    "toolCallId": tool_call_id,
                                    "toolName": event.part.tool_name,
                                    "input": event.part.args
                                })

                            elif isinstance(event, FunctionToolResultEvent):
                                # Tool has returned a result
                                tool_call_id = event.result.tool_call_id if hasattr(event.result, 'tool_call_id') else f"call_{uuid4().hex}"
                                status = "error" if hasattr(event.result, 'error') and event.result.error else "success"

                                # Emit ThreadProtocol tool_result event
                                await emit_threadprotocol_event({
                                    "event_type": "tool_result",
                                    "tool_name": event.result.tool_name,
                                    "result": event.result.content if hasattr(event.result, 'content') else str(event.result),
                                    "tool_call_id": tool_call_id,
                                    "status": status,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                })

                                # Emit VSP tool-output-available (boundary event, includes threadId)
                                await emit_vsp_event({
                                    "type": "tool-output-available",
                                    "toolCallId": tool_call_id,
                                    "output": event.result.content if hasattr(event.result, 'content') else str(event.result)
                                })

            # Get the final result
            result = agent_run.result

        # Return the final result
        return result