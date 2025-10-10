"""Demo of the Prometheus metrics provider.

This example shows how to use the Prometheus tool provider to query metrics.
"""

import asyncio

from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)


async def main():
    """Demonstrate Prometheus provider capabilities."""

    # Configure the provider
    config = PrometheusConfig(
        url="http://localhost:9090",  # Your Prometheus server
        disable_ssl=False,
    )

    # Use the provider
    async with PrometheusToolProvider(config=config) as provider:
        print("=" * 60)
        print("Prometheus Metrics Provider Demo")
        print("=" * 60)

        # 1. List available metrics
        print("\n1. Listing available metrics...")
        result = await provider.list_metrics()
        if result["status"] == "success":
            print(f"   Found {result['count']} metrics")
            if result["count"] > 0:
                print(f"   First 5 metrics: {result['metrics'][:5]}")
        else:
            print(f"   Error: {result['error']}")

        # 2. Query current memory usage
        print("\n2. Querying current memory usage...")
        result = await provider.query(query="node_memory_MemAvailable_bytes")
        if result["status"] == "success":
            print(f"   Query: {result['query']}")
            print(f"   Data points: {len(result['data'])}")
            if result["data"]:
                print(f"   Sample: {result['data'][0]}")
        else:
            print(f"   Error: {result['error']}")

        # 3. Query network throughput over time
        print("\n3. Querying network throughput (last 5 minutes)...")
        result = await provider.query_range(
            query="rate(node_network_transmit_bytes_total[1m])",
            start_time="5m",
            end_time="now",
            step="30s",
        )
        if result["status"] == "success":
            print(f"   Query: {result['query']}")
            print(f"   Time range: {result['start_time']} to {result['end_time']}")
            print(f"   Step: {result['step']}")
            print(f"   Data points: {len(result['data'])}")
        else:
            print(f"   Error: {result['error']}")

        # 4. Demonstrate tool routing
        print("\n4. Using tool routing mechanism...")
        tool_name = provider._make_tool_name("query")
        result = await provider.resolve_tool_call(tool_name=tool_name, args={"query": "up"})
        if result["status"] == "success":
            print(f"   Tool: {tool_name}")
            print(f"   Result: {len(result['data'])} data points")
        else:
            print(f"   Error: {result['error']}")

        # 5. Show tool schemas (what the LLM sees)
        print("\n5. Tool schemas available to LLM:")
        schemas = provider.create_tool_schemas()
        for schema in schemas:
            print(f"   - {schema.name}")
            print(f"     Description: {schema.description[:80]}...")

        print("\n" + "=" * 60)
        print("Demo complete!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
