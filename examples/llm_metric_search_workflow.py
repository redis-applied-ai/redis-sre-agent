#!/usr/bin/env python3
"""Simulate how an LLM would search for and query metrics.

This demonstrates the typical workflow:
1. User asks about a metric
2. LLM searches for available metrics
3. LLM finds the right metric
4. LLM queries the metric
"""

import asyncio

from redis_sre_agent.core.config import Settings
from redis_sre_agent.tools.manager import ToolManager


async def simulate_llm_workflow():
    """Simulate an LLM conversation about metrics."""

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
        async with ToolManager() as manager:
            print("=" * 70)
            print("LLM Metric Search Workflow Simulation")
            print("=" * 70)

            # Scenario 1: User asks about memory
            print("\n" + "=" * 70)
            print("SCENARIO 1: User asks 'How much memory is Redis using?'")
            print("=" * 70)

            print("\n[LLM Thinking]: I need to find Redis memory metrics...")
            print("[LLM Action]: Call list_metrics tool")

            # Step 1: List all metrics
            list_tool = next(t for t in manager.get_tools() if "list_metrics" in t.name)
            result = await manager.resolve_tool_call(list_tool.name, {})

            all_metrics = result["metrics"]
            print(f"[LLM]: Found {len(all_metrics)} total metrics")

            # Step 2: Filter for Redis memory metrics
            redis_memory = [m for m in all_metrics if "redis" in m and "memory" in m]
            print(f"[LLM]: Filtered to {len(redis_memory)} Redis memory metrics")
            print("[LLM]: Best match: redis_memory_used_bytes")

            # Step 3: Query the metric
            print("\n[LLM Action]: Query redis_memory_used_bytes")
            query_tool = next(
                t
                for t in manager.get_tools()
                if "prometheus" in t.name and "query" in t.name and "range" not in t.name
            )
            result = await manager.resolve_tool_call(
                query_tool.name, {"query": "redis_memory_used_bytes"}
            )

            if result["status"] == "success" and result["data"]:
                value = int(result["data"][0]["value"][1])
                mb = value / (1024 * 1024)
                print(f"[LLM Response]: Redis is using {mb:.2f} MB of memory")

            # Scenario 2: User asks about connections
            print("\n" + "=" * 70)
            print("SCENARIO 2: User asks 'How many clients are connected?'")
            print("=" * 70)

            print("\n[LLM Thinking]: I need to find Redis connection metrics...")
            print("[LLM]: I already have the metric list from before")

            # Filter for connection metrics
            redis_connections = [
                m for m in all_metrics if "redis" in m and ("client" in m or "connection" in m)
            ]
            print(f"[LLM]: Found {len(redis_connections)} connection-related metrics")
            print(f"[LLM]: Candidates: {redis_connections[:5]}")
            print("[LLM]: Best match: redis_connected_clients")

            # Query the metric
            print("\n[LLM Action]: Query redis_connected_clients")
            result = await manager.resolve_tool_call(
                query_tool.name, {"query": "redis_connected_clients"}
            )

            if result["status"] == "success" and result["data"]:
                value = int(result["data"][0]["value"][1])
                print(f"[LLM Response]: There are {value} clients connected to Redis")

            # Scenario 3: User asks about performance
            print("\n" + "=" * 70)
            print("SCENARIO 3: User asks 'What's the Redis hit rate?'")
            print("=" * 70)

            print("\n[LLM Thinking]: Hit rate requires keyspace hits and misses...")

            # Search for keyspace metrics
            keyspace_metrics = [m for m in all_metrics if "redis" in m and "keyspace" in m]
            print(f"[LLM]: Found {len(keyspace_metrics)} keyspace metrics")
            print(f"[LLM]: Found: {keyspace_metrics}")
            print("[LLM]: I need both redis_keyspace_hits_total and redis_keyspace_misses_total")

            # Query hit rate using PromQL
            print("\n[LLM Action]: Calculate hit rate with PromQL")
            promql = (
                "rate(redis_keyspace_hits_total[1m]) / "
                "(rate(redis_keyspace_hits_total[1m]) + rate(redis_keyspace_misses_total[1m]))"
            )
            print(f"[LLM]: Using query: {promql}")

            result = await manager.resolve_tool_call(query_tool.name, {"query": promql})

            if result["status"] == "success" and result["data"]:
                value = float(result["data"][0]["value"][1])
                percentage = value * 100
                print(f"[LLM Response]: Redis hit rate is {percentage:.1f}%")
            else:
                print("[LLM Response]: No hit/miss data available yet (Redis just started)")

            # Scenario 4: User asks about trends
            print("\n" + "=" * 70)
            print("SCENARIO 4: User asks 'Show me memory usage over the last hour'")
            print("=" * 70)

            print("\n[LLM Thinking]: This needs a range query...")
            print("[LLM Action]: Use query_range tool")

            range_tool = next(t for t in manager.get_tools() if "query_range" in t.name)
            result = await manager.resolve_tool_call(
                range_tool.name,
                {
                    "query": "redis_memory_used_bytes",
                    "start_time": "1h",
                    "end_time": "now",
                    "step": "5m",
                },
            )

            if result["status"] == "success" and result["data"]:
                data_points = len(result["data"][0]["values"]) if result["data"] else 0
                print(f"[LLM]: Retrieved {data_points} data points over the last hour")
                print("[LLM Response]: Memory usage has been stable around 25 MB for the past hour")

            # Summary
            print("\n" + "=" * 70)
            print("WORKFLOW SUMMARY")
            print("=" * 70)
            print("""
The LLM workflow for metric search:

1. **Discovery**: Call list_metrics() to get all available metrics
   - Returns 1,165 metrics in this case
   - LLM caches this list for the conversation

2. **Filtering**: Search the metric list for relevant names
   - Filter by keywords (redis, memory, connection, etc.)
   - Match patterns (e.g., metrics ending in _total for counters)
   - Identify the best metric for the user's question

3. **Querying**: Use the appropriate query tool
   - query() for instant values ("How much memory?")
   - query_range() for trends ("Show me the last hour")
   - Complex PromQL for calculations ("What's the hit rate?")

4. **Response**: Format the data for the user
   - Convert bytes to MB/GB
   - Calculate percentages
   - Describe trends

This enables the LLM to answer questions like:
- "How much memory is Redis using?" → Find + query redis_memory_used_bytes
- "How many clients?" → Find + query redis_connected_clients
- "What's the hit rate?" → Find + calculate with PromQL
- "Show me trends" → Find + query_range with time window
            """)
            print("=" * 70)

    finally:
        config_module.settings = original_settings


if __name__ == "__main__":
    asyncio.run(simulate_llm_workflow())
