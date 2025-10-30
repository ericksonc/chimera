"""Test widget hydration from Blueprint to runtime."""

import sys
sys.path.insert(0, '/Users/ericksonc/appdev/chimera')

from core.agent import Agent
from core.widgets.qa_widget import QAWidget, QAWidgetConfig
from core.threadprotocol.blueprint import InlineAgentConfig, ComponentConfig


def test_widget_hydration():
    """Test that widgets can be hydrated from blueprint config."""
    print("=" * 60)
    print("Testing Widget Hydration")
    print("=" * 60)

    # 1. Create an agent with a widget programmatically
    print("\n1. Creating agent with QAWidget...")
    qa_widget = QAWidget()
    qa_widget.instance_id = "qa-001"

    agent = Agent(
        id="agent-123",
        name="Test Agent",
        base_prompt="You are a test agent",
        description="Test agent for widget hydration",
        widgets=[qa_widget]
    )
    print(f"   Created agent with {len(agent.widgets)} widget(s)")

    # 2. Serialize to blueprint config
    print("\n2. Serializing to blueprint...")
    config = agent.to_blueprint_config()
    print(f"   Agent config type: {type(config).__name__}")
    print(f"   Agent ID: {config.id}")
    print(f"   Widget configs: {len(config.widgets)}")
    if config.widgets:
        print(f"   First widget class: {config.widgets[0].class_name}")
        print(f"   First widget instance_id: {config.widgets[0].instance_id}")

    # 3. Deserialize back to agent (hydrate widgets)
    print("\n3. Deserializing from blueprint (hydrating widgets)...")
    hydrated_agent = Agent.from_blueprint_config(config)
    print(f"   Hydrated agent ID: {hydrated_agent.id}")
    print(f"   Hydrated widgets: {len(hydrated_agent.widgets)}")

    # 4. Verify hydrated widget works
    print("\n4. Verifying hydrated widget...")
    if hydrated_agent.widgets:
        widget = hydrated_agent.widgets[0]
        print(f"   Widget type: {type(widget).__name__}")
        print(f"   Widget instance_id: {widget.instance_id}")

        # Test widget functionality
        instructions = widget.get_instructions(None)
        if "2341" in instructions:
            print("   ✓ Secret number found in instructions!")
        else:
            print("   ✗ Secret number NOT found!")

        toolset = widget.get_toolset()
        if toolset:
            print("   ✓ Toolset provided!")
        else:
            print("   ✗ No toolset!")

    # 5. Verify round-trip identity
    print("\n5. Verifying round-trip...")
    if (agent.id == hydrated_agent.id and
        agent.name == hydrated_agent.name and
        len(agent.widgets) == len(hydrated_agent.widgets)):
        print("   ✓ Round-trip successful!")
    else:
        print("   ✗ Round-trip failed!")

    print("\n" + "=" * 60)
    print("Widget Hydration Test Complete!")
    print("=" * 60)


if __name__ == "__main__":
    test_widget_hydration()
