"""
Integration tests for multi-turn conversation flow.

Tests the complete flow:
1. Create thread
2. Send initial message
3. Get response
4. Send follow-up message
5. Verify agent has context from previous messages
"""

import pytest

from redis_sre_agent.core.tasks import process_agent_turn
from redis_sre_agent.core.thread_state import get_thread_manager


@pytest.fixture
async def thread_manager(redis_container):
    """Get the thread manager for testing (depends on redis_container to ensure URL is set)."""
    manager = get_thread_manager()
    yield manager


@pytest.fixture
async def test_thread(thread_manager):
    """Create a test thread."""
    thread_id = await thread_manager.create_thread(
        user_id="test-user", session_id="test-session", initial_context={"test": True}
    )

    # Return a simple object with thread_id
    class TestThread:
        def __init__(self, tid):
            self.thread_id = tid

    yield TestThread(thread_id)
    # Cleanup - delete thread after test
    try:
        await thread_manager.delete_thread(thread_id)
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.integration
@pytest.mark.asyncio
async def test_initial_message_creates_conversation_history(thread_manager, test_thread):
    """Test that the first message creates conversation history."""
    thread_id = test_thread.thread_id

    # Send initial message
    await process_agent_turn(thread_id=thread_id, message="What is Redis?")

    # Load thread state
    thread_state = await thread_manager.get_thread_state(thread_id)

    # Verify messages were saved
    messages = thread_state.context.get("messages", [])
    assert len(messages) >= 2, "Should have at least user message and assistant response"

    # Verify message structure
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "What is Redis?"

    assistant_msg = messages[1]
    assert assistant_msg["role"] == "assistant"
    assert len(assistant_msg["content"]) > 0

    # Verify no tool messages in saved history
    for msg in messages:
        assert msg["role"] in ["user", "assistant"], f"Found unexpected role: {msg['role']}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_follow_up_message_has_context(thread_manager, test_thread):
    """Test that follow-up messages have access to previous conversation."""
    thread_id = test_thread.thread_id

    # Send initial message
    await process_agent_turn(
        thread_id=thread_id,
        message="My name is Alice and I work with Redis.",
    )

    # Send follow-up asking about previous context
    await process_agent_turn(
        thread_id=thread_id,
        message="What is my name?",
    )

    # Load thread state
    thread_state = await thread_manager.get_thread_state(thread_id)
    messages = thread_state.context.get("messages", [])

    # Debug: print all messages
    print(f"\n=== CONVERSATION HISTORY ({len(messages)} messages) ===")
    for i, msg in enumerate(messages):
        print(f"{i + 1}. {msg['role']}: {msg['content'][:100]}")
    print("=" * 50)

    # Should have 4 messages: user1, assistant1, user2, assistant2
    assert len(messages) >= 4, f"Expected at least 4 messages, got {len(messages)}"

    # Verify the conversation flow
    assert messages[0]["content"] == "My name is Alice and I work with Redis."
    assert messages[2]["content"] == "What is my name?"

    # The assistant's response should mention "Alice"
    final_response = messages[3]["content"]
    assert "Alice" in final_response or "alice" in final_response.lower(), (
        f"Agent should remember the name Alice. Response: {final_response}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_tool_messages_in_saved_history(thread_manager, test_thread):
    """Test that tool messages are not saved to thread context."""
    thread_id = test_thread.thread_id

    # Send a message that will trigger tool use
    await process_agent_turn(
        thread_id=thread_id,
        message="Search the knowledge base for Redis persistence",
    )

    # Load thread state
    thread_state = await thread_manager.get_thread_state(thread_id)
    messages = thread_state.context.get("messages", [])

    # Verify no tool messages
    for msg in messages:
        assert msg["role"] != "tool", "Tool messages should not be saved to thread context"
        assert msg["role"] in ["user", "assistant"], f"Unexpected role: {msg['role']}"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(
    reason="Agent asks for instance clarification instead of doing arithmetic - needs prompt fix"
)
async def test_multiple_follow_ups_maintain_context(thread_manager, test_thread):
    """Test that multiple follow-up messages maintain full conversation context."""
    thread_id = test_thread.thread_id

    # Turn 1
    await process_agent_turn(
        thread_id=thread_id,
        message="I have a Redis cluster with 3 nodes.",
    )

    # Turn 2
    await process_agent_turn(
        thread_id=thread_id,
        message="Each node has 16GB of memory.",
    )

    # Turn 3 - ask about info from turn 1 and 2
    await process_agent_turn(
        thread_id=thread_id,
        message="How much total memory do I have?",
    )

    # Load thread state
    thread_state = await thread_manager.get_thread_state(thread_id)
    messages = thread_state.context.get("messages", [])

    # Should have 6 messages (3 turns x 2 messages each)
    assert len(messages) >= 6, f"Expected at least 6 messages, got {len(messages)}"

    # Verify all user messages are present
    user_messages = [msg for msg in messages if msg["role"] == "user"]
    assert len(user_messages) == 3
    assert "3 nodes" in user_messages[0]["content"]
    assert "16GB" in user_messages[1]["content"]
    assert "total memory" in user_messages[2]["content"]

    # The final response should calculate 48GB (3 nodes * 16GB)
    final_response = messages[-1]["content"]
    assert "48" in final_response or "forty-eight" in final_response.lower(), (
        f"Agent should calculate total memory. Response: {final_response}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_langgraph_checkpointer_integration(thread_manager, test_thread):
    """Test that LangGraph checkpointer works with our thread state."""
    thread_id = test_thread.thread_id

    # Send initial message
    await process_agent_turn(
        thread_id=thread_id,
        message="Remember this number: 42",
    )

    # Get the thread state
    thread_state_1 = await thread_manager.get_thread_state(thread_id)
    messages_1 = thread_state_1.context.get("messages", [])

    # Send follow-up
    await process_agent_turn(
        thread_id=thread_id,
        message="What number did I ask you to remember?",
    )

    # Get updated thread state
    thread_state_2 = await thread_manager.get_thread_state(thread_id)
    messages_2 = thread_state_2.context.get("messages", [])

    # Verify messages accumulated
    assert len(messages_2) > len(messages_1), "Messages should accumulate"

    # Verify the agent remembered
    final_response = messages_2[-1]["content"]
    assert "42" in final_response, (
        f"Agent should remember the number 42. Response: {final_response}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_duplicate_messages_in_history(thread_manager, test_thread):
    """Test that messages are not duplicated in thread history."""
    thread_id = test_thread.thread_id

    # Send message
    await process_agent_turn(
        thread_id=thread_id,
        message="Hello, this is a test message.",
    )

    # Load thread state
    thread_state = await thread_manager.get_thread_state(thread_id)
    messages = thread_state.context.get("messages", [])

    # Check for duplicates
    seen_messages = set()
    for msg in messages:
        msg_key = (msg["role"], msg["content"], msg.get("timestamp"))
        assert msg_key not in seen_messages, (
            f"Duplicate message found: {msg['role']}: {msg['content'][:50]}"
        )
        seen_messages.add(msg_key)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_different_threads_have_separate_history(thread_manager):
    """Test that different threads maintain separate conversation histories."""
    # Create two separate threads
    thread1_id = await thread_manager.create_thread(
        user_id="test-user", session_id="session-1", initial_context={"test": True}
    )

    thread2_id = await thread_manager.create_thread(
        user_id="test-user", session_id="session-2", initial_context={"test": True}
    )

    class TestThread:
        def __init__(self, tid):
            self.thread_id = tid

    thread1 = TestThread(thread1_id)
    thread2 = TestThread(thread2_id)

    # Send different messages to each thread
    await process_agent_turn(thread_id=thread1.thread_id, message="My favorite color is blue")

    await process_agent_turn(thread_id=thread2.thread_id, message="My favorite color is red")

    # Load both thread states
    thread1_state = await thread_manager.get_thread_state(thread1.thread_id)
    thread2_state = await thread_manager.get_thread_state(thread2.thread_id)

    thread1_messages = thread1_state.context.get("messages", [])
    thread2_messages = thread2_state.context.get("messages", [])

    # Verify each thread has its own messages
    assert len(thread1_messages) >= 2, "Thread 1 should have messages"
    assert len(thread2_messages) >= 2, "Thread 2 should have messages"

    # Verify thread 1 mentions blue
    thread1_user_msg = thread1_messages[0]["content"]
    assert "blue" in thread1_user_msg.lower(), f"Thread 1 should mention blue: {thread1_user_msg}"
    assert "red" not in thread1_user_msg.lower(), (
        f"Thread 1 should not mention red: {thread1_user_msg}"
    )

    # Verify thread 2 mentions red
    thread2_user_msg = thread2_messages[0]["content"]
    assert "red" in thread2_user_msg.lower(), f"Thread 2 should mention red: {thread2_user_msg}"
    assert "blue" not in thread2_user_msg.lower(), (
        f"Thread 2 should not mention blue: {thread2_user_msg}"
    )

    # Cleanup
    try:
        await thread_manager.delete_thread(thread1_id)
        await thread_manager.delete_thread(thread2_id)
    except Exception:
        pass


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
