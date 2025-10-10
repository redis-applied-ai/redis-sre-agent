#!/usr/bin/env python3
"""Test querying Redis-specific metrics from Prometheus."""

import asyncio

from redis_sre_agent.tools.metrics.prometheus import (
    PrometheusConfig,
    PrometheusToolProvider,
)


async def main():
    """Query Redis metrics from Prometheus."""

    config = PrometheusConfig(url="http://localhost:9090")

    async with PrometheusToolProvider(config=config) as provider:
        print("=" * 70)
        print("Redis Metrics from Prometheus")
        print("=" * 70)

        # Query Redis connected clients
        print("\n1. Redis Connected Clients:")
        result = await provider.query(query="redis_connected_clients")
        if result["status"] == "success" and result["data"]:
            for item in result["data"]:
                value = item["value"][1]
                print(f"   Connected clients: {value}")
        else:
            print(f"   No data or error: {result.get('error', 'No data')}")

        # Query Redis memory usage
        print("\n2. Redis Memory Usage:")
        result = await provider.query(query="redis_memory_used_bytes")
        if result["status"] == "success" and result["data"]:
            for item in result["data"]:
                value = int(item["value"][1])
                mb = value / (1024 * 1024)
                print(f"   Memory used: {mb:.2f} MB ({value} bytes)")
        else:
            print(f"   No data or error: {result.get('error', 'No data')}")

        # Query Redis uptime
        print("\n3. Redis Uptime:")
        result = await provider.query(query="redis_uptime_in_seconds")
        if result["status"] == "success" and result["data"]:
            for item in result["data"]:
                seconds = int(item["value"][1])
                minutes = seconds / 60
                print(f"   Uptime: {minutes:.1f} minutes ({seconds} seconds)")
        else:
            print(f"   No data or error: {result.get('error', 'No data')}")

        # Query Redis commands per second
        print("\n4. Redis Commands Per Second (last 1 minute):")
        result = await provider.query(query="rate(redis_commands_processed_total[1m])")
        if result["status"] == "success" and result["data"]:
            for item in result["data"]:
                value = float(item["value"][1])
                print(f"   Commands/sec: {value:.2f}")
        else:
            print(f"   No data or error: {result.get('error', 'No data')}")

        # Query keyspace hits/misses ratio
        print("\n5. Redis Keyspace Hit Rate:")
        result = await provider.query(
            query="rate(redis_keyspace_hits_total[1m]) / "
            "(rate(redis_keyspace_hits_total[1m]) + rate(redis_keyspace_misses_total[1m]))"
        )
        if result["status"] == "success" and result["data"]:
            for item in result["data"]:
                value = float(item["value"][1])
                percentage = value * 100
                print(f"   Hit rate: {percentage:.1f}%")
        else:
            print(f"   No data or error: {result.get('error', 'No data')}")

        # List all Redis metrics
        print("\n6. All Redis Metrics Available:")
        result = await provider.list_metrics()
        if result["status"] == "success":
            redis_metrics = [m for m in result["metrics"] if m.startswith("redis_")]
            print(f"   Found {len(redis_metrics)} Redis metrics")
            print(f"   Examples: {redis_metrics[:10]}")

        print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
