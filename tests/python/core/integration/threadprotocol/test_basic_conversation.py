"""Test the most basic thing: user says something, agent responds.

This is the simplest possible test of GenericTransformer.
If this doesn't work, nothing will work.
"""

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from chimera_core.threadprotocol.transformer import GenericTransformer


def test_simple_user_agent_exchange():
    """User says 'Hi', agent says 'Hello'. Convert to ModelMessages."""

    events = [
        # User turn
        {
            "type": "data-user-turn-start",
            "data": {"userId": "00000000-0000-0000-0000-000000000000"},
        },
        {"type": "data-user-message", "data": {"content": "Hi, r u there"}},
        {"type": "data-user-turn-end"},
        # Agent turn - agent responds with text
        {
            "type": "data-agent-start",
            "data": {"agentId": "jarvis-basic", "agentName": "Jarvis - Basic"},
        },
        {
            "type": "text-complete",
            "id": "text_1",
            "content": "Yes, I'm here. How can I assist you?",
        },
        {
            "type": "data-agent-finish",
            "data": {"agentId": "jarvis-basic", "agentName": "Jarvis - Basic"},
        },
    ]

    transformer = GenericTransformer()
    messages = transformer.transform(events)

    print(f"\n=== Transformed {len(events)} events into {len(messages)} messages ===")
    for i, msg in enumerate(messages):
        print(f"Message {i}: {type(msg).__name__}")
        for j, part in enumerate(msg.parts):
            print(f"  Part {j}: {type(part).__name__}")
            if hasattr(part, "content"):
                print(f"    content: {part.content}")

    # We should have exactly 2 messages
    assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"

    # Message 0: User's prompt
    assert isinstance(messages[0], ModelRequest), (
        f"Message 0 should be ModelRequest, got {type(messages[0])}"
    )
    assert len(messages[0].parts) == 1
    assert isinstance(messages[0].parts[0], UserPromptPart)
    assert messages[0].parts[0].content == "Hi, r u there"

    # Message 1: Agent's response
    assert isinstance(messages[1], ModelResponse), (
        f"Message 1 should be ModelResponse, got {type(messages[1])}"
    )
    assert len(messages[1].parts) == 1
    assert isinstance(messages[1].parts[0], TextPart)
    assert messages[1].parts[0].content == "Yes, I'm here. How can I assist you?"

    print("\n✓ Test passed: User message and agent response both present")


def test_two_exchanges():
    """Two back-and-forth exchanges."""

    events = [
        # Exchange 1
        {
            "type": "data-user-turn-start",
            "data": {"userId": "00000000-0000-0000-0000-000000000000"},
        },
        {"type": "data-user-message", "data": {"content": "What's the weather?"}},
        {"type": "data-user-turn-end"},
        {"type": "data-agent-start", "data": {"agentId": "agent-1", "agentName": "Test"}},
        {"type": "text-complete", "id": "text_1", "content": "It's sunny!"},
        {"type": "data-agent-finish", "data": {"agentId": "agent-1", "agentName": "Test"}},
        # Exchange 2
        {
            "type": "data-user-turn-start",
            "data": {"userId": "00000000-0000-0000-0000-000000000000"},
        },
        {"type": "data-user-message", "data": {"content": "Thanks!"}},
        {"type": "data-user-turn-end"},
        {"type": "data-agent-start", "data": {"agentId": "agent-1", "agentName": "Test"}},
        {"type": "text-complete", "id": "text_2", "content": "You're welcome!"},
        {"type": "data-agent-finish", "data": {"agentId": "agent-1", "agentName": "Test"}},
    ]

    transformer = GenericTransformer()
    messages = transformer.transform(events)

    # Should be 4 messages: Request, Response, Request, Response
    assert len(messages) == 4, f"Expected 4 messages, got {len(messages)}"

    assert isinstance(messages[0], ModelRequest)
    assert messages[0].parts[0].content == "What's the weather?"

    assert isinstance(messages[1], ModelResponse)
    assert messages[1].parts[0].content == "It's sunny!"

    assert isinstance(messages[2], ModelRequest)
    assert messages[2].parts[0].content == "Thanks!"

    assert isinstance(messages[3], ModelResponse)
    assert messages[3].parts[0].content == "You're welcome!"

    print("\n✓ Test passed: Two exchanges correctly alternating Request/Response")
