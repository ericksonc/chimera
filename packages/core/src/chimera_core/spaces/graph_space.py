"""GraphSpace - A pydantic-graph-based Space implementation for orchestrating agent execution through a finite state machine.

Each node is a full agent turn with complete streaming infrastructure, using EmptyTransformer
for stateless execution and typed outputs for data flow and routing.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Literal

from pydantic_graph.beta import Graph, GraphBuilder, StepContext

from chimera_core.protocols.space_decision import TurnDecision
from chimera_core.spaces.base import Space
from chimera_core.threadprotocol.transformer import EmptyTransformer

if TYPE_CHECKING:
    from pydantic_ai.agent import AgentRunResult

    from chimera_core.agent import Agent
    from chimera_core.protocols.transformer import ThreadProtocolTransformer
    from chimera_core.threadprotocol.blueprint import ComponentConfig, SpaceConfig
    from chimera_core.types.user_input import UserInput


@dataclass
class GraphState:
    """Mutable state shared across all graph nodes.

    IMPORTANT: Following pydantic-graph best practices, GraphState should
    contain ONLY data that evolves during graph execution (counters, metrics,
    accumulated results). For GraphSpace, node outputs flow via ctx.inputs
    between nodes, so GraphState is minimal/empty.

    Dependencies (things that don't change) go in GraphDeps instead.
    """

    pass  # Currently empty - may add execution metrics/counters in future


@dataclass
class GraphDeps:
    """Immutable dependencies injected into graph nodes.

    These are resources/context needed for execution but never change.
    Naturally thread-safe for parallel execution (read-only).
    """

    space: GraphSpace  # The containing GraphSpace instance
    agents: dict[str, Agent]  # Available agents for node execution
    ctx: StepContext  # Thread's execution context (read-only access)
    transformer: ThreadProtocolTransformer  # For message history (EmptyTransformer)
    message: str  # Original user message (immutable)
    user_input: UserInput | None  # User input object (immutable)


@dataclass
class NodeConfig:
    """Configuration for a single graph node."""

    id: str
    instructions: str
    output_type: str | list[dict]  # Type spec or union specs
    agent_id: str | None = None
    timeout: int = 60  # seconds
    label: str | None = None


@dataclass
class EdgeConfig:
    """Configuration for graph edges."""

    from_node: str
    to_node: str
    type: Literal["simple", "conditional"] = "simple"
    routes: list[RouteConfig] | None = None  # For conditional edges


@dataclass
class RouteConfig:
    """Configuration for conditional route."""

    kind: str  # Must match discriminator value
    to_node: str


@dataclass
class GraphSpaceConfig:
    """Configuration for GraphSpace from Blueprint."""

    nodes: list[NodeConfig]
    edges: list[EdgeConfig]


class GraphExecutionError(Exception):
    """Raised when graph execution fails."""

    def __init__(self, node_id: str, original_error: Exception):
        self.node_id = node_id
        self.original_error = original_error
        super().__init__(f"Node {node_id} failed: {original_error}")


class GraphSpace(Space):
    """A Space that orchestrates agent execution through a pydantic-graph FSM.

    Implements DecidableSpace protocol (structural typing) to control multi-turn execution.
    Each blueprint node becomes one turn, with GraphSpace tracking progress and providing
    the next node's instructions when continuing.
    """

    def __init__(self):
        super().__init__()
        self._graph: Graph[GraphState, GraphDeps, str, Any] | None = None
        self._graph_config: GraphSpaceConfig | None = None
        self._current_node_index: int = 0
        self._node_id_to_index: dict[str, int] = {}

    @property
    def output_type(self) -> type | list[type]:
        """Dynamic output type based on current node being executed."""
        if not self._graph_config or self._current_node_index >= len(self._graph_config.nodes):
            return str  # Default fallback

        current_node = self._graph_config.nodes[self._current_node_index]
        return self.resolve_output_type(current_node.output_type)

    @property
    def active_agent(self) -> Agent:
        """The currently active agent for the current node."""
        if not self._graph_config or self._current_node_index >= len(self._graph_config.nodes):
            raise ValueError("No active agent - graph not configured or invalid node index")

        current_node = self._graph_config.nodes[self._current_node_index]

        # Use node-specific agent if specified, otherwise use first agent in space
        if current_node.agent_id:
            agent = next((a for a in self._agents if a.id == current_node.agent_id), None)
            if not agent:
                raise ValueError(f"Agent with ID {current_node.agent_id} not found in space")
            return agent
        elif self._agents:
            return self._agents[0]
        else:
            raise ValueError("No agents configured in GraphSpace")

    def _get_all_agents(self) -> List[Agent]:
        """Get all agents in this space."""
        return self._agents

    def get_transformer(self) -> EmptyTransformer:
        """Get EmptyTransformer for stateless node execution."""
        return EmptyTransformer()

    def should_continue_turn(self, last_output: Any) -> TurnDecision:
        """Determine if graph has more nodes to execute.

        Called by thread.py after each agent turn to decide whether to continue.

        Args:
            last_output: The output from the node that just completed
                        # TODO: Properly constrain this type variable based on PAI's AgentOutputT implementation
                        # For now, using Any to support str, int, float, Pydantic models, etc.

        Returns:
            TurnDecision with:
            - "continue" if more nodes remain (provides next node's instructions)
            - "complete" if all nodes executed
        """
        # Check if we have a graph configured
        if not self._graph_config:
            return TurnDecision(decision="complete")

        # Check if current index is within bounds
        if self._current_node_index >= len(self._graph_config.nodes):
            # All nodes executed - reset for next user input
            self._current_node_index = 0
            return TurnDecision(decision="complete")

        # More nodes remain - provide the previous output as the next prompt
        # The actual node instructions get combined with this in run_stream()
        # We pass the output directly so run_stream() can apply templates correctly
        return TurnDecision(
            decision="continue",
            next_prompt=str(last_output),  # Pass the output value as the message
        )

    def resolve_output_type(self, type_spec: str | list[dict]) -> type | list[type]:
        """Convert blueprint type specification to Python type.

        GraphSpace decides how to interpret type strings.
        Other Spaces can have different interpretations.
        """

        # Handle union types (for discriminated unions)
        if isinstance(type_spec, list):
            return [self._resolve_single(t["class"]) for t in type_spec]

        # Handle single type
        return self._resolve_single(type_spec)

    def _resolve_single(self, type_str: str) -> type:
        """Resolve single type string to Python type.

        GraphSpace-specific type resolution. The Space decides
        what "int", "float", etc. mean in its context.
        """

        # GraphSpace's primitives (it decides what these mean)
        graph_primitives = {
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            # GraphSpace might interpret "number" as Union[int, float]
            "number": int | float,
        }

        if type_str in graph_primitives:
            return graph_primitives[type_str]

        # Dynamic import for complex types
        if "." in type_str:
            try:
                module_path, class_name = type_str.rsplit(".", 1)
                module = importlib.import_module(module_path)
                return getattr(module, class_name)
            except (ImportError, AttributeError) as e:
                raise ValueError(
                    f"GraphSpace cannot resolve type '{type_str}': {e}. "
                    f"Ensure the module exists and the class is importable."
                ) from e

        raise ValueError(
            f"GraphSpace cannot resolve type: '{type_str}'. "
            f"Supported primitives: {', '.join(graph_primitives.keys())}. "
            f"For custom types, use fully qualified names like 'module.path.ClassName'."
        )

    async def run_stream(
        self, ctx: StepContext, message: str, user_input: UserInput | None = None
    ) -> AgentRunResult:
        """Execute a SINGLE graph node with full streaming infrastructure.

        This is called once per turn by thread.py. GraphSpace executes one node,
        then should_continue_turn() tells thread.py whether to loop back.

        Multi-node execution happens through thread.py's turn loop, NOT here.

        Args:
            ctx: Step context from thread.py
            message: The message for this node (user input for first node, previous output for subsequent)
            user_input: User input object (for tool approvals, etc.)

        Returns:
            AgentRunResult with the node's output
        """
        # Ensure graph is configured
        if not self._graph_config:
            raise ValueError("GraphSpace not configured - no graph_config set")

        # Check if we have a node to execute
        if self._current_node_index >= len(self._graph_config.nodes):
            raise ValueError(
                f"No node to execute at index {self._current_node_index}. "
                f"Graph has {len(self._graph_config.nodes)} nodes."
            )

        # Get current node config
        node_config = self._graph_config.nodes[self._current_node_index]

        # Format input for agent
        if self._current_node_index == 0:
            # First node gets original user message with instructions
            agent_message = f"{node_config.instructions}\n\n{message}"
        else:
            # Subsequent nodes: Apply template substitution
            # If instructions don't use {output}, that's fine - just raw instructions
            agent_message = self.apply_template(node_config.instructions, message)

        # Get agent for this node
        agent = self._get_agent_for_node(node_config)

        # Get transformer (EmptyTransformer for stateless execution)
        transformer = self.get_transformer()

        # Execute agent with full streaming infrastructure
        try:
            result = await asyncio.wait_for(
                agent.run_stream(
                    ctx=ctx, transformer=transformer, message=agent_message, user_input=user_input
                ),
                timeout=node_config.timeout,
            )
        except asyncio.TimeoutError:
            raise GraphExecutionError(
                node_config.id,
                TimeoutError(f"Node {node_config.id} exceeded {node_config.timeout}s timeout"),
            )

        # Increment node index for next turn
        self._current_node_index += 1

        # Return result (output flows to next turn via thread.py's turn loop)
        return result

    def _get_agent_for_node(self, node_config: NodeConfig) -> Agent:
        """Get the agent for a specific node."""
        if node_config.agent_id:
            agent = next((a for a in self._agents if a.id == node_config.agent_id), None)
            if not agent:
                raise ValueError(f"Agent with ID {node_config.agent_id} not found in space")
            return agent
        elif self._agents:
            return self._agents[0]
        else:
            raise ValueError("No agents configured in GraphSpace")

    def _serialize_for_thread(self, output_value: Any) -> str:
        """Convert typed output to string for thread.py compatibility."""
        if output_value is None:
            return ""
        elif isinstance(output_value, str):
            return output_value
        elif isinstance(output_value, (int, float, bool)):
            return str(output_value)
        else:
            # For complex types, use JSON serialization
            return json.dumps(output_value, indent=2, default=str)

    def _build_graph(self) -> Graph[GraphState, GraphDeps, str, Any]:
        """Build pydantic-graph from blueprint configuration."""

        self._graph_builder = GraphBuilder(
            state_type=GraphState, deps_type=GraphDeps, input_type=str, output_type=Any
        )

        # Create node steps
        node_steps = {}
        for i, node_config in enumerate(self._graph_config.nodes):
            node_step = self._create_node_step(node_config, i)
            node_steps[node_config.id] = node_step
            self._node_id_to_index[node_config.id] = i

        # Connect start node to first node
        if self._graph_config.nodes:
            first_node = self._graph_config.nodes[0]
            self._graph_builder.add_edge(self._graph_builder.start_node, node_steps[first_node.id])

        # Add edges between nodes
        for edge_config in self._graph_config.edges:
            if edge_config.type == "simple":
                self._graph_builder.add_edge(
                    node_steps[edge_config.from_node], node_steps[edge_config.to_node]
                )
            elif edge_config.type == "conditional":
                # TODO: Implement conditional edges for Phase 3
                pass

        # Connect last node to end node
        if self._graph_config.nodes:
            last_node = self._graph_config.nodes[-1]
            self._graph_builder.add_edge(node_steps[last_node.id], self._graph_builder.end_node)

        return self._graph_builder.build()

    def _create_node_step(self, node_config: NodeConfig, node_index: int) -> Any:
        """Create a pydantic-graph step function for a node."""

        @self._graph_builder.step(node_id=node_config.id)
        async def execute_node(ctx: StepContext[GraphState, GraphDeps, Any]) -> Any:
            """Execute a single graph node as a full agent turn."""

            # Get dependencies (immutable resources)
            space = ctx.deps.space
            thread_ctx = ctx.deps.ctx  # Thread's execution context
            transformer = ctx.deps.transformer  # EmptyTransformer for this node
            user_input = ctx.deps.user_input  # User input (if any)

            # Get node configuration
            # Note: current_node_index is tracked in space._current_node_index
            node_config = space._graph_config.nodes[space._current_node_index]

            # Format input for agent
            if space._current_node_index == 0:
                # First node gets original user message from deps
                agent_message = f"{node_config.instructions}\n\n{ctx.deps.message}"
            else:
                # Subsequent nodes get previous output via ctx.inputs (pydantic-graph pattern)
                previous_output = ctx.inputs

                # Check if instructions contain templates
                if "{output" in node_config.instructions:
                    # Apply template substitution
                    agent_message = space.apply_template(node_config.instructions, previous_output)
                else:
                    # Backwards compatible - append input
                    agent_message = (
                        f"{node_config.instructions}\n\n"
                        f"Input: {space._serialize_for_prompt(previous_output)}"
                    )

            # Get agent for this node
            agent = (
                ctx.deps.agents.get(node_config.agent_id)
                if node_config.agent_id
                else space.active_agent
            )

            # Execute agent with full streaming infrastructure
            # Use asyncio.wait_for for timeout
            try:
                result = await asyncio.wait_for(
                    agent.run_stream(
                        ctx=thread_ctx,  # Thread context from deps
                        transformer=transformer,  # EmptyTransformer from deps
                        message=agent_message,
                        user_input=user_input,  # User input from deps
                    ),
                    timeout=node_config.timeout,
                )
            except asyncio.TimeoutError:
                raise GraphExecutionError(
                    node_config.id,
                    TimeoutError(f"Node execution exceeded {node_config.timeout}s timeout"),
                )

            # Increment node index for next execution
            space._current_node_index += 1

            # Return typed output for next node (flows via ctx.inputs to next step)
            return result.output

        return execute_node

    def _serialize_for_prompt(self, value: Any) -> str:
        """Convert typed value to string for agent prompt."""
        if value is None:
            return ""
        elif hasattr(value, "model_dump_json"):  # Pydantic model
            return value.model_dump_json(indent=2)
        elif isinstance(value, (list, dict)):
            return json.dumps(value, indent=2, default=str)
        else:
            return str(value)

    # ========================================================================
    # Template System for Node Instructions
    # ========================================================================

    def apply_template(self, template: str, output_value: Any) -> str:
        """Apply template substitution to node instructions.

        Replaces {output} with the previous node's output value, or
        {output.field} with dot-notation field access for structured outputs.

        Args:
            template: Instruction string with {output} or {output.field} placeholders
            output_value: The previous node's output value

        Returns:
            Instruction string with templates replaced by actual values

        Examples:
            apply_template("Divide {output} by 3", 100)
            → "Divide 100 by 3"

            apply_template("Story about {output.name} in {output.location}", character_obj)
            → "Story about Zorblat in Andromeda"
        """
        import re

        def replace_placeholder(match: re.Match) -> str:
            path = match.group(1).strip()

            # Handle {output} - use the whole value
            if path == "output":
                return self._serialize_for_prompt(output_value)

            # Handle {output.field.subfield} - dot notation
            if path.startswith("output."):
                field_path = path[7:]  # Remove "output." prefix
                value = self._resolve_field_path(output_value, field_path)
                return self._serialize_for_prompt(value)

            # Invalid template variable - return as-is
            return match.group(0)  # Keep the {invalid} in output

        return re.sub(r"\{([^}]+)\}", replace_placeholder, template)

    def _resolve_field_path(self, obj: Any, field_path: str) -> Any:
        """Resolve dot-notation field path in object.

        Args:
            obj: Object to traverse (Pydantic model, dict, etc.)
            field_path: Dot-separated path like "name" or "metadata.author"

        Returns:
            Resolved value

        Raises:
            ValueError: If field path cannot be resolved
        """
        parts = field_path.split(".")
        current = obj

        for part in parts:
            try:
                if isinstance(current, dict):
                    current = current[part]
                elif hasattr(current, part):
                    current = getattr(current, part)
                else:
                    raise ValueError(
                        f"Cannot access '{part}' in field path '{field_path}'. "
                        f"Object type: {type(current).__name__}"
                    )
            except (KeyError, AttributeError) as e:
                raise ValueError(f"Field path '{field_path}' failed at '{part}': {e}") from e

        return current

    # ========================================================================
    # BlueprintProtocol Serialization
    # ========================================================================

    def _get_all_agents(self) -> List[Agent]:
        """Get all agents in this space.

        Returns:
            List of Agent instances
        """
        return self._agents

    def to_blueprint_config(self) -> "ComponentConfig":
        """Serialize GraphSpace to BlueprintProtocol format.

        Returns:
            ComponentConfig with GraphSpace metadata and graph configuration
        """
        from chimera_core.threadprotocol.blueprint import ComponentConfig

        # Serialize graph configuration
        config_dict = (
            {
                "nodes": [
                    {
                        "id": node.id,
                        "instructions": node.instructions,
                        "output_type": node.output_type,
                        "agent_id": node.agent_id,
                        "timeout": node.timeout,
                        "label": node.label,
                    }
                    for node in self._graph_config.nodes
                ],
                "edges": [
                    {
                        "from_node": edge.from_node,
                        "to_node": edge.to_node,
                        "type": edge.type,
                        "routes": edge.routes,
                    }
                    for edge in self._graph_config.edges
                ],
            }
            if self._graph_config
            else {"nodes": [], "edges": []}
        )

        return ComponentConfig(
            class_name="core.spaces.graph_space.GraphSpace",
            version="1.0.0",
            instance_id=self.instance_id or "space",
            config=config_dict,
        )

    @classmethod
    def from_blueprint_config(cls, space_config: "SpaceConfig") -> "GraphSpace":
        """Deserialize GraphSpace from BlueprintProtocol format.

        Args:
            space_config: SpaceConfig from BlueprintProtocol

        Returns:
            GraphSpace instance with resolved agents and graph configuration
        """
        # Resolve agents using base class helper
        agents = cls._resolve_agents_from_config(space_config)

        # Create space instance
        space = cls()
        space._agents = agents
        space.instance_id = "space"

        # Deserialize graph configuration
        config_dict = space_config.config or {}
        nodes_data = config_dict.get("nodes", [])
        edges_data = config_dict.get("edges", [])

        # Create NodeConfig objects
        nodes = [
            NodeConfig(
                id=node["id"],
                instructions=node["instructions"],
                output_type=node["output_type"],
                agent_id=node.get("agent_id"),
                timeout=node.get("timeout", 60),
                label=node.get("label"),
            )
            for node in nodes_data
        ]

        # Create EdgeConfig objects
        edges = [
            EdgeConfig(
                from_node=edge["from_node"],
                to_node=edge["to_node"],
                type=edge.get("type", "simple"),
                routes=edge.get("routes"),
            )
            for edge in edges_data
        ]

        # Set graph configuration
        space._graph_config = GraphSpaceConfig(nodes=nodes, edges=edges)

        return space
