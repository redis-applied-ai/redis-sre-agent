#!/usr/bin/env python3
"""
Demonstrate metric search patterns with the Prometheus provider.

This script shows various ways to search for metrics using the search_metrics tool.
"""

import asyncio

from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)


async def main():
    """Demonstrate various metric search patterns."""

    config = PrometheusConfig(url="http://localhost:9090")

    async with PrometheusToolProvider(config=config) as provider:
        print("=" * 70)
        print("Prometheus Metric Search Examples")
        print("=" * 70)

        # Pattern 1: Search by prefix
        print("\n1. Search by Prefix")
        print("-" * 70)

        result = await provider.search_metrics(pattern="redis_")
        print(f"   redis_* metrics: {result['count']}")
        print(f"   Examples: {result['metrics'][:5]}")

        result = await provider.search_metrics(pattern="node_")
        print(f"   node_* metrics: {result['count']}")
        print(f"   Examples: {result['metrics'][:5]}")

        # Pattern 2: Search by keyword
        print("\n2. Search by Keyword")
        print("-" * 70)

        result = await provider.search_metrics(pattern="memory")
        print(f"   'memory' metrics: {result['count']}")
        print(f"   Examples: {result['metrics'][:5]}")

        result = await provider.search_metrics(pattern="network")
        print(f"   'network' metrics: {result['count']}")
        print(f"   Examples: {result['metrics'][:5]}")

        # Pattern 3: Specific search
        print("\n3. Specific Search")
        print("-" * 70)

        result = await provider.search_metrics(pattern="redis_memory")
        print(f"   'redis_memory' metrics: {result['count']}")
        print(f"   All: {result['metrics']}")

        result = await provider.search_metrics(pattern="redis_connected")
        print(f"   'redis_connected' metrics: {result['count']}")
        print(f"   All: {result['metrics']}")

        # Pattern 4: List all metrics
        print("\n4. List All Metrics (empty pattern)")
        print("-" * 70)

        result = await provider.search_metrics(pattern="")
        print(f"   Total metrics: {result['count']}")
        print(f"   First 10: {result['metrics'][:10]}")

        # Pattern 5: Via ToolManager (how LLM uses it)
        print("\n5. Via ToolManager (LLM Usage)")
        print("-" * 70)

        from redis_sre_agent.tools.manager import ToolManager

        async with ToolManager() as manager:
            # Find the search_metrics tool
            tools = manager.get_tools()
            search_tool = next((t for t in tools if "search_metrics" in t.name), None)

            if search_tool:
                print(f"   Tool found: {search_tool.name}")
                print(f"   Description: {search_tool.description[:80]}...")

                # Execute search
                result = await manager.resolve_tool_call(
                    tool_name=search_tool.name, args={"pattern": "redis_keyspace"}
                )

                print(f"   Search 'redis_keyspace': {result['count']} metrics")
                print(f"   Results: {result['metrics']}")

        print("\n" + "=" * 70)
        print("Summary:")
        print("  - search_metrics(pattern='') lists all metrics")
        print("  - search_metrics(pattern='redis') finds Redis metrics")
        print("  - search_metrics(pattern='redis_memory') is very specific")
        print("  - More efficient than retrieving all metrics and filtering")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
