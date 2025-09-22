#!/usr/bin/env python3
"""
Functional test to verify that the LLM knows about and can use fragment retrieval tools.

This test validates that:
1. The LLM has access to fragment retrieval tools
2. The LLM understands when to use these tools
3. The LLM can properly extract document_hash and chunk_index from search results
4. The LLM can make follow-up calls to get complete documents or context
"""

import asyncio
import logging

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent

# Set up logging to see what the LLM is doing
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_llm_fragment_awareness():
    """Test that the LLM knows about and can use fragment retrieval tools."""
    print("🧠 Testing LLM Fragment Retrieval Awareness")
    print("=" * 55)

    # Initialize the agent
    print("🤖 Initializing SRE Agent...")
    agent = SRELangGraphAgent()

    # Check that the tools are available
    print("\n📋 Checking Available Tools...")
    available_tools = [tool["function"]["name"] for tool in agent.llm_with_tools.kwargs["tools"]]

    required_tools = [
        "search_knowledge_base",
        "get_all_document_fragments",
        "get_related_document_fragments"
    ]

    print(f"Available tools: {available_tools}")

    for tool in required_tools:
        if tool in available_tools:
            print(f"✅ {tool} - Available")
        else:
            print(f"❌ {tool} - Missing")
            return False

    print("\n🎯 Testing LLM Fragment Retrieval Behavior...")

    # Test 1: Ask a question that should trigger fragment retrieval
    test_query = """
    I need comprehensive information about Redis Enterprise migration.
    Please search for relevant information and if you find fragments of documents,
    make sure to get the complete context or full documents to provide me with
    thorough guidance.
    """

    print(f"\n📝 Test Query: {test_query}")
    print("\n🔄 Agent Processing...")

    try:
        # Run the agent
        session_id = "test_session"
        result = await agent.process_query(test_query, session_id=session_id, user_id="test_user")

        print("\n📊 Agent Response:")
        print(f"Response: {result}")

        # Get the thread state to see what tool calls were made
        thread_state = await agent.get_thread_state(session_id)
        messages = thread_state.get('messages', [])
        tool_calls_made = []

        for message in messages:
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_calls_made.append({
                        'name': tool_call['name'],
                        'args': tool_call['args']
                    })

        print("\n🔧 Tool Calls Made:")
        for i, call in enumerate(tool_calls_made, 1):
            print(f"  {i}. {call['name']}")
            print(f"     Args: {call['args']}")

        # Analyze the tool usage
        search_calls = [c for c in tool_calls_made if c['name'] == 'search_knowledge_base']
        fragment_calls = [c for c in tool_calls_made if c['name'] in ['get_all_document_fragments', 'get_related_document_fragments']]

        print("\n📈 Analysis:")
        print(f"  Search calls: {len(search_calls)}")
        print(f"  Fragment retrieval calls: {len(fragment_calls)}")

        # Test success criteria
        success_criteria = {
            "Made search call": len(search_calls) > 0,
            "Made fragment retrieval call": len(fragment_calls) > 0,
            "Used document_hash correctly": False,
            "Provided comprehensive response": len(str(result)) > 500
        }

        # Check if document_hash was used correctly
        for call in fragment_calls:
            if 'document_hash' in call['args'] and call['args']['document_hash']:
                success_criteria["Used document_hash correctly"] = True
                break

        print("\n✅ Success Criteria:")
        for criterion, passed in success_criteria.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status}: {criterion}")

        overall_success = all(success_criteria.values())

        if overall_success:
            print("\n🎉 OVERALL: SUCCESS - LLM properly uses fragment retrieval tools!")
        else:
            print("\n⚠️  OVERALL: PARTIAL SUCCESS - Some criteria not met")

        return overall_success, success_criteria, tool_calls_made

    except Exception as e:
        print(f"\n❌ Error during agent execution: {e}")
        return False, {}, []


async def test_llm_tool_descriptions():
    """Test that the LLM has proper tool descriptions."""
    print("\n🔍 Testing Tool Descriptions...")

    agent = SRELangGraphAgent()

    # Find the fragment retrieval tools
    tools = agent.llm_with_tools.kwargs["tools"]

    fragment_tools = [
        tool for tool in tools
        if tool["function"]["name"] in ["get_all_document_fragments", "get_related_document_fragments"]
    ]

    print(f"\nFound {len(fragment_tools)} fragment retrieval tools:")

    for tool in fragment_tools:
        func = tool["function"]
        print(f"\n📋 Tool: {func['name']}")
        print(f"   Description: {func['description']}")
        print(f"   Parameters: {list(func['parameters']['properties'].keys())}")

        # Check description quality
        description = func['description']
        quality_checks = {
            "Mentions document_hash": "document_hash" in description,
            "Explains when to use": any(word in description.lower() for word in ["when", "use this", "essential"]),
            "References search results": "search results" in description,
            "Clear purpose": len(description) > 50
        }

        print("   Quality checks:")
        for check, passed in quality_checks.items():
            status = "✅" if passed else "❌"
            print(f"     {status} {check}")

    return len(fragment_tools) == 2


async def main():
    """Run all LLM fragment awareness tests."""
    print("🚀 Starting LLM Fragment Retrieval Awareness Tests")
    print("=" * 60)

    # Test 1: Tool descriptions
    print("\n" + "="*60)
    print("TEST 1: Tool Descriptions")
    print("="*60)

    descriptions_ok = await test_llm_tool_descriptions()

    # Test 2: Functional behavior
    print("\n" + "="*60)
    print("TEST 2: Functional Behavior")
    print("="*60)

    behavior_ok, criteria, tool_calls = await test_llm_fragment_awareness()

    # Summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)

    print(f"✅ Tool Descriptions: {'PASS' if descriptions_ok else 'FAIL'}")
    print(f"✅ Functional Behavior: {'PASS' if behavior_ok else 'PARTIAL'}")

    if behavior_ok and descriptions_ok:
        print("\n🎉 ALL TESTS PASSED!")
        print("   The LLM is fully aware of fragment retrieval capabilities")
        print("   and can use them appropriately.")
    else:
        print("\n⚠️  SOME TESTS FAILED")
        print("   The LLM may not be fully utilizing fragment retrieval tools.")

        if not descriptions_ok:
            print("   - Tool descriptions need improvement")
        if not behavior_ok:
            print("   - LLM behavior needs adjustment")
            print(f"   - Failed criteria: {[k for k, v in criteria.items() if not v]}")

    print("\n📊 Tool Usage Summary:")
    print(f"   Total tool calls made: {len(tool_calls)}")
    for call in tool_calls:
        print(f"   - {call['name']}")


if __name__ == "__main__":
    asyncio.run(main())
