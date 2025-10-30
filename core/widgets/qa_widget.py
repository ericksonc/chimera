"""QAWidget - Test widget for verifying widget infrastructure.

Provides a simple print_console tool and injects instructions with a secret number
to verify that widget instructions and tools are properly integrated.
"""

from dataclasses import dataclass
from typing import Any, Optional
from ..widget import Widget
from ..threadprotocol.blueprint import ComponentConfig
from pydantic_ai import FunctionToolset


@dataclass
class QAWidgetConfig:
    """Configuration for QAWidget.

    This is the BlueprintT type - stored in BlueprintProtocol at Turn 0.
    """
    enabled: bool = True


class QAWidget(Widget[QAWidgetConfig]):
    """Test widget that provides print_console tool and verifiable instructions.

    This widget serves as a simple test case to verify:
    1. Instruction injection works (via the secret number)
    2. Tool provision works (via print_console)
    3. Blueprint serialization/deserialization works

    Type parameters:
    - QAWidgetConfig: Turn 0 configuration (BlueprintT)
    - Any: No runtime mutations (MutationT) - this is a stateless widget
    """

    # Component metadata (inherited from BasePlugin)
    component_class_name: str = "chimera.widgets.QAWidget"
    component_version: str = "1.0.0"

    def __init__(self):
        """Initialize QAWidget."""
        super().__init__()
        self.enabled: bool = True

    def get_instructions(self, state) -> str:
        """Inject instructions with secret number for verification.

        This method is called by Agent during setup to collect instructions
        from all widgets. The secret number verifies that instructions are
        actually being injected.

        Args:
            state: Read-only thread state

        Returns:
            Instructions string to be added to agent's system prompt
        """
        if not self.enabled:
            return None

        return """
QA Widget Instructions:
- You have access to a print_console tool that prints messages to the console
- Use it to output debug information or important messages
- The secret number is 2341
"""

    def get_toolset(self) -> Optional[FunctionToolset]:
        """Provide the print_console tool.

        This method is called by Agent during setup to collect tools
        from all widgets.

        Returns:
            FunctionToolset containing print_console tool
        """
        if not self.enabled:
            return None

        toolset = FunctionToolset()

        @toolset.tool
        def print_console(message: str) -> str:
            """Print a message to the console.

            Use this to output debug information or important messages
            that should be visible in the server logs.

            Args:
                message: The message to print

            Returns:
                Confirmation that the message was printed
            """
            print(f"[QAWidget Console]: {message}")
            return f"Printed to console: {message}"

        return toolset

    # BlueprintProtocol Serialization (inherited abstract methods)

    def to_blueprint_config(self) -> ComponentConfig[QAWidgetConfig]:
        """Serialize this widget instance to BlueprintProtocol format.

        Returns:
            ComponentConfig with typed QAWidgetConfig
        """
        return ComponentConfig(
            class_name=self.component_class_name,
            version=self.component_version,
            instance_id=self.instance_id,
            config=QAWidgetConfig(enabled=self.enabled)
        )

    @classmethod
    def from_blueprint_config(cls, config: ComponentConfig[QAWidgetConfig]) -> "QAWidget":
        """Deserialize widget instance from BlueprintProtocol format.

        Args:
            config: ComponentConfig with QAWidgetConfig

        Returns:
            QAWidget instance
        """
        widget = cls()
        widget.instance_id = config.instance_id
        widget.enabled = config.config.enabled
        return widget
