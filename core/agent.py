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
import yaml

from pydantic_ai import Agent as PAIAgent, ModelMessage

# Import Pydantic AI types for node processing
from pydantic_ai._agent_graph import CallToolsNode
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent
)

import logfire

# from .exceptions import ConfigurationError, AgentNotConfiguredError # TODO: custom exception types?
from .models import create_model

from .protocols import ReadableThreadState

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
    

    async def run_stream(
        self,
        state: ReadableThreadState,
        prompt,  # note- if this AgentTurn was preceded by another agent turn, "prompt" is 
        # essentially a representation of the previous agent's turn (from Pydantic AI's POV, not ThreadProtocol's POV)
    ):
        """
        Run the Pydantic AI agent with streaming token deltas.

        Uses Pydantic AI's .iter() on the _pai_agent

        Yields:
            Token deltas as they arrive from the LLM
        """

        # Setup PAI agent
        pai_agent, message_history = self._setup_pai_agent(state)

        # Run the agent turn usiny Pydantic AI's agent.iter()
        result = self._run_pai_agent(pai_agent, message_history=message_history)


    def _setup_pai_agent(self, state):
        """Setup PAI agent with all configuration

        Returns:
            Tuple of (pai_agent, message_history, deps)
        """

        #####
        ## TODO: implement model precedence approach, for now, just use agent-specified model > global default.
        ## MODEL PRECEDENCE:
        ## more narrow = overrides
        ## user override of model string > specifying model for agent > model for cell > model for thread_config > global default model
        model_string = self._get_model_string

        # Create the model using the factory
        model = create_model(model_string)

        # Create PAI agent fresh for this run with ChimeraDeps type
        pai_agent = PAIAgent(
            model=model,
            # output_type=output_type,  # TODO: allow for other output_types. for now, only str (text) output.
            system_prompt=self._system_prompt,
            deps_type=ChimeraDeps  # TODO: define universal deps type we pass to agent. 
        )

        # TODO: Register widget tools with the PAI agent

        # TODO: Register all dynamic instructions collected from lifecycle hooks

        # TODO: Choose concrete implementation of core/protocols/transformer.py to be used (based on space)

        # Create ChimeraDeps from state (with ThreadDeps if available)

        # temporary stub for output vars
        message_history: list[ModelMessage] = []

        return (pai_agent, message_history)

    async def _run_pai_agent(self, pai_agent:PAIAgent, message_history:List[ModelMessage]):
        """Run the PAI agent using agent.iter() and capture ThreadProtocol events.

        Uses agent.iter() to iterate through execution nodes, capturing tool calls
        and returns for ThreadProtocol. Processes CallToolsNode to extract real-time
        tool execution events.

        Args:
            pai_agent: The Pydantic AI agent instance
            pai_messages: The message history in PAI format
            chimera_deps: ChimeraDeps with aggregator, message emitter, and state

        Returns:
            AgentRunResult: The same result as pai_agent.run() would return
        """


        # Use agent.iter() to run through the execution graph
        async with pai_agent.iter(
            message_history=message_history,
            deps=chimera_deps # TODO: centralized way to define this
        ) as agent_run:
            # Iterate through all nodes
            async for node in agent_run:

                # See designdocs/reference/stream_text_to_iter_migration.md + git_clones/pydantic_ai/
                if PAIAgent.is_model_request_node(node):
                    # Add node.stream() processing here
                    pass

                # TOOL EXECUTION NODE - Capture tool calls and returns
                elif isinstance(node, CallToolsNode):
                    async for event in node:
                        if isinstance(event, FunctionToolCallEvent):
                            thread_builder.add_tool_call(
                                tool_name=event.part.tool_name,
                                args=event.part.args_as_dict(),
                                call_id=event.part.tool_call_id
                            )

                        elif isinstance(event, FunctionToolResultEvent):
                            # Tool finished executing
                            # Determine status based on whether there's an error
                            status = "error" if event.result.error else "success"
                            thread_builder.add_tool_return(
                                tool_name=event.result.tool_name,
                                result=event.result.content,
                                call_id=event.result.tool_call_id,
                                status=status
                                )

            # Get the final result
            result = agent_run.result

        # Extract usage
            usage = agent_run.usage

        # Complete agent turn in ThreadProtocol by adding in usage
        thread_builder.complete_agent_turn(usage=agent_run.usage)

        return result