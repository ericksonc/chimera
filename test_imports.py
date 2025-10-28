#!/usr/bin/env python3
"""Quick test to verify our imports work."""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

async def test_imports():
    """Test that all our core imports work."""
    print("Testing imports...")

    # Test protocol imports
    from core.protocols.readable_thread_state import ReadableThreadState, ActiveSpace, ActiveAgent
    print("✓ Protocol imports work")

    # Test base imports
    from core.base import Widget, Space, GenericSpace, Agent, Blueprint, ThreadState
    print("✓ Base class imports work")

    # Test threadprotocol imports
    from core.threadprotocol.writer import ThreadProtocolWriter
    from core.threadprotocol.reader import ThreadProtocolReader
    from core.threadprotocol.blueprint import create_simple_blueprint
    from core.threadprotocol.transformer import GenericTransformer
    print("✓ ThreadProtocol imports work")

    # Test convenience imports
    from core import (
        ThreadProtocolWriter,
        ThreadProtocolReader,
        create_simple_blueprint,
        GenericTransformer
    )
    print("✓ Convenience imports work")

    # Quick functional test - create a blueprint
    blueprint = create_simple_blueprint(
        agent_name="TestAgent",
        agent_prompt="You are a test agent",
        model_string="openai:gpt-4o-mini"
    )
    print(f"✓ Created blueprint for thread: {blueprint['thread_id']}")

    print("\nAll imports successful! Ready to continue building.")

if __name__ == "__main__":
    asyncio.run(test_imports())