#!/usr/bin/env python3
"""Test the new search_metrics tool."""

import asyncio

from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)


async def main():
    """Test metric search functionality."""

    config = PrometheusConfig(url="http://localhost:9090")

    async with PrometheusToolProvider(config=config) as provider:
        print("=" * 70)
        print("Testing Metric Search Tool")
        print("=" * 70)

        # Test 1: Search for Redis metrics
        print("\n1. Search for 'redis' metrics:")
        result = await provider.search_metrics(pattern="redis")
        if result["status"] == "success":
            print(f"   Found {result['count']} metrics")
            print(f"   First 10: {result['metrics'][:10]}")

        # Test 2: Search for memory metrics
        print("\n2. Search for 'memory' metrics:")
        result = await provider.search_metrics(pattern="memory")
        if result["status"] == "success":
            print(f"   Found {result['count']} metrics")
            print(f"   First 10: {result['metrics'][:10]}")

        # Test 3: Search for specific pattern
        print("\n3. Search for 'redis_memory' (more specific):")
        result = await provider.search_metrics(pattern="redis_memory")
        if result["status"] == "success":
            print(f"   Found {result['count']} metrics")
            print(f"   All: {result['metrics']}")

        # Test 4: Search for network metrics
        print("\n4. Search for 'network' metrics:")
        result = await provider.search_metrics(pattern="network")
        if result["status"] == "success":
            print(f"   Found {result['count']} metrics")
            print(f"   First 10: {result['metrics'][:10]}")

        # Test 5: Search for connected/connection metrics
        print("\n5. Search for 'connected' metrics:")
        result = await provider.search_metrics(pattern="connected")
        if result["status"] == "success":
            print(f"   Found {result['count']} metrics")
            print(f"   All: {result['metrics']}")

        # Test 6: Compare with list_metrics
        print("\n6. Comparison: search vs list+filter")

        # Using search
        search_result = await provider.search_metrics(pattern="redis_keyspace")
        search_count = search_result["count"]

        # Using list + filter
        list_result = await provider.list_metrics()
        all_metrics = list_result["metrics"]
        filtered = [m for m in all_metrics if "redis_keyspace" in m.lower()]
        filter_count = len(filtered)

        print(f"   search_metrics('redis_keyspace'): {search_count} metrics")
        print(f"   list_metrics() + filter: {filter_count} metrics")
        print(f"   Results match: {search_count == filter_count}")

        print("\n" + "=" * 70)
        print("Summary:")
        print("  - search_metrics() provides targeted metric discovery")
        print("  - More efficient than list_metrics() + client-side filtering")
        print("  - LLM can use this to quickly find relevant metrics")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
