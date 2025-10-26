"""
Agent representation for the Chimera MAS.

This module defines the Agent class that both holds configuration
and provides Pydantic AI integration for running agents.
"""

from dataclasses import dataclass, field
from typing import Any, List, TYPE_CHECKING, Optional
from typing_extensions import TypedDict
from uuid import UUID, uuid4

from pydantic_ai import Agent as PAIAgent, ModelMessage
from pydantic_ai.tools import RunContext as PAIRunContext

# Import Pydantic AI types for node processing
from pydantic_ai._agent_graph import CallToolsNode
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent
)

import logfire
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .exceptions import ConfigurationError, AgentNotConfiguredError
from .models import create_model
from translation.pydantic_ai import translate_for_agent

from .interfaces import ReadableThreadState


logfire.configure(send_to_logfire='if-token-present')  
logfire.instrument_pydantic_ai() 
logfire.instrument_httpx(capture_all=True)  

@dataclass
class Agent:
    # TODO: Create ConfigurationProtocol, load it here
    """
    Agent configuration and runtime functionality.
    
    Combines identity, prompts, and Pydantic AI integration.
    """
    
    async def run(
        self,
        state: ReadableThreadState
    ) -> Any:
        """
        Run the Pydantic AI agent with message history.

        Args:
            state: The current ThreadState containing cell, messages, and aggregator

        Returns:
            Pydantic AI AgentRunResult containing the agent's output
        """

        # Setup PAI agent
        pai_agent, pai_messages, chimera_deps = self._setup_pai_agent(state)

        # Run with message history and ChimeraDeps
        result = await self._run_pai_agent(
            pai_agent,
            pai_messages,
            chimera_deps
        )

        return result

    async def run_stream(
        self,
        state: 'ReadableThreadState'
    ):
        """
        Run the Pydantic AI agent with streaming token deltas.

        Uses Pydantic AI's .iter() on the _pai_agent

        Yields:
            Token deltas as they arrive from the LLM
        """

        # Setup PAI agent
        pai_agent, pai_messages, chimera_deps = self._setup_pai_agent(state)

        # Stream using run_stream
        async with pai_agent.run_stream(
            message_history=pai_messages,
            deps=chimera_deps
        ) as result:
            async for chunk in result.stream_text(delta=True):
                yield chunk

    def _setup_pai_agent(self, state, cell):
        """Setup PAI agent with all configuration

        Returns:
            Tuple of (pai_agent, pai_messages, chimera_deps)
        """
        # Get configuration from the cell RIGHT NOW
        output_type = cell.get_output_type_for_agent(self)

        # Build system prompt from current cell's values
        parts = []
        if cell.cell_wallpaper:
            parts.append(f"Cell Context: {cell.cell_wallpaper}")
        if hasattr(cell, 'cell_instructions') and cell.cell_instructions:
            parts.append(cell.cell_instructions)
        system_prompt = "\n\n".join(parts) if parts else ""

        #####
        ## TODO:
        ## MODEL PRECEDENCE:
        ## more narrow = overrides
        ## user override of model string > specifying model for agent > model for cell > model for thread_config > global default model
        model_string = self._get_model_string

        # Create the model using the factory
        model = create_model(model_string)

        # Create PAI agent fresh for this run with ChimeraDeps type
        pai_agent = PAIAgent(
            model=model,
            output_type=output_type,
            system_prompt=system_prompt,
            deps_type=ChimeraDeps
        )

        # Register widget tools with the PAI agent
        if cell.widgets:
            for widget in cell.widgets:
                widget.register_tools_with_agent(pai_agent, self.agent_id)

        # Register dynamic instructions handler
        @pai_agent.instructions
        def add_dynamic_instructions(ctx: PAIRunContext[ChimeraDeps]) -> str:
            # TODO: Assemble "final" instructions
            pass
            

        # Read ThreadProtocol, generate list of modelmessages
        pai_messages:List[ModelMessage] = self._generate_model_messages()

        # Create ChimeraDeps from state (with ThreadDeps if available)

        return (pai_agent, pai_messages, chimera_deps)

    async def _run_pai_agent(self, pai_agent:PAIAgent, pai_messages, chimera_deps):
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
            message_history=pai_messages,
            deps=chimera_deps
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