#!/usr/bin/env python3
"""Examples of searching for available metrics in Prometheus."""

import asyncio

from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)


async def search_metrics_examples():
    """Show different ways to search for metrics."""

    config = PrometheusConfig(url="http://localhost:9090")

    async with PrometheusToolProvider(config=config) as provider:
        print("=" * 70)
        print("Searching for Metrics in Prometheus")
        print("=" * 70)

        # 1. List ALL metrics
        print("\n1. List all available metrics:")
        result = await provider.list_metrics()

        if result["status"] == "success":
            all_metrics = result["metrics"]
            print(f"   Total metrics: {result['count']}")
            print(f"   First 10: {all_metrics[:10]}")

        # 2. Search for Redis metrics
        print("\n2. Search for Redis-specific metrics:")
        if result["status"] == "success":
            redis_metrics = [m for m in all_metrics if m.startswith("redis_")]
            print(f"   Found {len(redis_metrics)} Redis metrics")
            print("   Examples:")
            for metric in redis_metrics[:10]:
                print(f"     - {metric}")

        # 3. Search for memory-related metrics
        print("\n3. Search for memory-related metrics:")
        if result["status"] == "success":
            memory_metrics = [m for m in all_metrics if "memory" in m.lower()]
            print(f"   Found {len(memory_metrics)} memory metrics")
            print("   Examples:")
            for metric in memory_metrics[:10]:
                print(f"     - {metric}")

        # 4. Search for network metrics
        print("\n4. Search for network-related metrics:")
        if result["status"] == "success":
            network_metrics = [m for m in all_metrics if "network" in m.lower()]
            print(f"   Found {len(network_metrics)} network metrics")
            print("   Examples:")
            for metric in network_metrics[:10]:
                print(f"     - {metric}")

        # 5. Search by category (node, redis, go, etc.)
        print("\n5. Search by metric prefix:")
        if result["status"] == "success":
            prefixes = {}
            for metric in all_metrics:
                prefix = metric.split("_")[0]
                prefixes[prefix] = prefixes.get(prefix, 0) + 1

            print("   Metric categories:")
            for prefix, count in sorted(prefixes.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"     - {prefix}: {count} metrics")

        # 6. Search for specific patterns
        print("\n6. Search for rate/counter metrics:")
        if result["status"] == "success":
            rate_metrics = [m for m in all_metrics if m.endswith("_total")]
            print(f"   Found {len(rate_metrics)} counter metrics (ending in _total)")
            print("   Examples:")
            for metric in rate_metrics[:10]:
                print(f"     - {metric}")

        print("\n" + "=" * 70)


async def search_via_tool_manager():
    """Show how the LLM would search for metrics via ToolManager."""

    from redis_sre_agent.core.config import Settings
    from redis_sre_agent.tools.manager import ToolManager

    # Configure settings
    settings = Settings()
    settings.tool_providers = [
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider"
    ]

    # Patch global settings
    import redis_sre_agent.core.config as config_module

    original_settings = config_module.settings
    config_module.settings = settings

    try:
        print("\n" + "=" * 70)
        print("Searching via ToolManager (how the LLM does it)")
        print("=" * 70)

        async with ToolManager() as manager:
            # Find the list_metrics tool
            tools = manager.get_tools()
            list_metrics_tool = next((t for t in tools if "list_metrics" in t.name), None)

            if list_metrics_tool:
                print(f"\n1. Tool found: {list_metrics_tool.name}")
                print(f"   Description: {list_metrics_tool.description[:80]}...")

                # Execute the tool (this is what the LLM does)
                print("\n2. Executing tool...")
                result = await manager.resolve_tool_call(
                    tool_name=list_metrics_tool.name,
                    args={},  # No arguments needed
                )

                if result["status"] == "success":
                    print(f"   ✓ Success! Found {result['count']} metrics")

                    # LLM can then filter the results
                    all_metrics = result["metrics"]
                    redis_metrics = [m for m in all_metrics if "redis" in m.lower()]
                    print("\n3. LLM filters for 'redis' metrics:")
                    print(f"   Found {len(redis_metrics)} Redis metrics")
                    print(f"   Examples: {redis_metrics[:5]}")

    finally:
        config_module.settings = original_settings


async def main():
    """Run all examples."""
    await search_metrics_examples()
    await search_via_tool_manager()


if __name__ == "__main__":
    asyncio.run(main())
