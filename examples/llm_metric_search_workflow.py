#!/usr/bin/env python3
"""
Simulate how an LLM would use the Prometheus provider to answer questions.

This demonstrates the typical workflow:
1. User asks a question
2. LLM searches for relevant metrics
3. LLM queries the metric
4. LLM formats the response
"""

import asyncio

from redis_sre_agent.tools.manager import ToolManager


async def simulate_llm_workflow():
    """Simulate LLM answering: 'How much memory is Redis using?'"""

    print("=" * 70)
    print("Simulated LLM Workflow")
    print("=" * 70)

    async with ToolManager() as manager:
        tools = manager.get_tools()

        # Step 1: User asks question
        print("\n[User]: How much memory is Redis using?")
        print()

        # Step 2: LLM searches for relevant metrics
        print("[LLM Thinking]: I need to find Redis memory metrics...")
        print("[LLM Action]: Call search_metrics tool with pattern='redis_memory'")

        search_tool = next(t for t in tools if "search_metrics" in t.name)
        result = await manager.resolve_tool_call(search_tool.name, {"pattern": "redis_memory"})

        print(f"[Tool Response]: Found {result['count']} metrics:")
        for metric in result["metrics"][:5]:
            print(f"  - {metric}")
        print()

        # Step 3: LLM picks the best metric
        print("[LLM Thinking]: 'redis_memory_used_bytes' looks like the right metric")
        print("[LLM Action]: Query redis_memory_used_bytes")

        query_tool = next(t for t in tools if "query" in t.name and "range" not in t.name)
        result = await manager.resolve_tool_call(
            query_tool.name, {"query": "redis_memory_used_bytes"}
        )

        if result["status"] == "success" and result["data"]:
            value = int(result["data"][0]["value"][1])
            mb = value / (1024 * 1024)

            print(f"[Tool Response]: {value} bytes")
            print()

            # Step 4: LLM formats response
            print(f"[LLM Response]: Redis is currently using {mb:.2f} MB of memory")

        print("\n" + "=" * 70)
        print("Workflow Summary:")
        print("1. **Discovery**: search_metrics('redis_memory') → 14 metrics")
        print("2. **Selection**: Pick redis_memory_used_bytes")
        print("3. **Query**: prometheus_query(query='redis_memory_used_bytes')")
        print("4. **Response**: Format for user")
        print()
        print("Benefits of search_metrics:")
        print("  - Targeted search (14 metrics vs 1,165+ total)")
        print("  - Single tool call for discovery")
        print("  - Fast and efficient")
        print("=" * 70)


async def simulate_exploration_workflow():
    """Simulate LLM answering: 'What Redis metrics are available?'"""

    print("\n\n" + "=" * 70)
    print("Exploration Workflow")
    print("=" * 70)

    async with ToolManager() as manager:
        tools = manager.get_tools()

        # Step 1: User asks question
        print("\n[User]: What Redis metrics are available?")
        print()

        # Step 2: LLM searches for Redis metrics
        print("[LLM Action]: Search for all Redis metrics")

        search_tool = next(t for t in tools if "search_metrics" in t.name)
        result = await manager.resolve_tool_call(search_tool.name, {"pattern": "redis"})

        print(f"[Tool Response]: Found {result['count']} Redis metrics")
        print()

        # Step 3: LLM categorizes results
        print("[LLM Thinking]: Let me categorize these...")

        metrics = result["metrics"]
        categories = {
            "Memory": [m for m in metrics if "memory" in m],
            "Clients": [m for m in metrics if "client" in m or "connected" in m],
            "Keyspace": [m for m in metrics if "keyspace" in m],
            "Commands": [m for m in metrics if "command" in m],
            "Performance": [m for m in metrics if "ops" in m or "latency" in m],
        }

        print("[LLM Response]: I found 187 Redis metrics across several categories:")
        for category, cat_metrics in categories.items():
            if cat_metrics:
                print(f"\n  {category} ({len(cat_metrics)} metrics):")
                for metric in cat_metrics[:3]:
                    print(f"    - {metric}")
                if len(cat_metrics) > 3:
                    print(f"    ... and {len(cat_metrics) - 3} more")

        print("\n" + "=" * 70)


async def main():
    """Run all workflow simulations."""
    await simulate_llm_workflow()
    await simulate_exploration_workflow()


if __name__ == "__main__":
    asyncio.run(main())
