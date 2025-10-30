"""Quick test of QAWidget functionality."""

import sys
sys.path.insert(0, '/Users/ericksonc/appdev/chimera')

# Import directly to avoid thread.py initialization
from core.widgets.qa_widget import QAWidget, QAWidgetConfig
from core.threadprotocol.blueprint import ComponentConfig


def test_qa_widget():
    """Test QAWidget basic functionality."""
    print("=" * 60)
    print("Testing QAWidget")
    print("=" * 60)

    # 1. Create widget instance
    print("\n1. Creating QAWidget instance...")
    widget = QAWidget()
    widget.instance_id = "test-qa-001"
    print(f"   Created widget with instance_id: {widget.instance_id}")

    # 2. Test instruction injection
    print("\n2. Testing instruction injection...")
    instructions = widget.get_instructions(None)
    print(f"   Instructions:\n{instructions}")
    if "2341" in instructions:
        print("   ✓ Secret number found in instructions!")
    else:
        print("   ✗ Secret number NOT found in instructions!")

    # 3. Test tool provision
    print("\n3. Testing tool provision...")
    toolset = widget.get_toolset()
    if toolset:
        print("   ✓ Toolset provided")
        # Check what's in the toolset
        print(f"   Toolset type: {type(toolset)}")
        print(f"   Toolset dir: {[attr for attr in dir(toolset) if not attr.startswith('_')]}")
    else:
        print("   ✗ No toolset provided!")

    # 4. Test serialization
    print("\n4. Testing blueprint serialization...")
    config = widget.to_blueprint_config()
    print(f"   Serialized config:")
    print(f"   - class_name: {config.class_name}")
    print(f"   - version: {config.version}")
    print(f"   - instance_id: {config.instance_id}")
    print(f"   - config.enabled: {config.config.enabled}")

    # 5. Test deserialization
    print("\n5. Testing blueprint deserialization...")
    widget2 = QAWidget.from_blueprint_config(config)
    print(f"   Deserialized widget:")
    print(f"   - instance_id: {widget2.instance_id}")
    print(f"   - enabled: {widget2.enabled}")
    if widget2.instance_id == widget.instance_id:
        print("   ✓ Instance IDs match!")
    else:
        print("   ✗ Instance IDs do NOT match!")

    print("\n" + "=" * 60)
    print("QAWidget test complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_qa_widget()
