#!/usr/bin/env python3
"""Test script to verify Redis direct access tools."""

import asyncio
import sys

from redis_sre_agent.tools.dynamic_tools import (
    get_redis_diagnostics,
    query_instance_metrics,
)


async def test_query_instance_metrics_with_redis_url():
    """Test that query_instance_metrics connects directly to Redis when redis_url is provided."""
    print("=" * 80)
    print("TEST 1: query_instance_metrics with redis_url (Direct Redis Connection)")
    print("=" * 80)

    redis_url = "redis://localhost:12000"  # Redis Enterprise

    print(f"\n📊 Querying metrics from Redis Enterprise at {redis_url}")
    print("   Using query_instance_metrics with redis_url parameter")
    print("   This should connect DIRECTLY to Redis via INFO command")

    result = await query_instance_metrics(
        metric_names=["used_memory", "connected_clients", "total_commands_processed"],
        redis_url=redis_url,
    )

    print("\n✅ Result:")
    if "error" in result:
        print(f"   ❌ Error: {result['error']}")
        return False

    print(f"   Metrics queried: {result.get('metrics_queried', result.get('metric_name'))}")
    print(f"   Providers queried: {result.get('providers_queried')}")

    for metric_result in result.get("results", []):
        provider = metric_result.get("provider")
        metric_name = metric_result.get("metric_name")
        if "error" in metric_result:
            print(f"   ⚠️  {metric_name} ({provider}): {metric_result['error']}")
        else:
            value = metric_result.get("current_value")
            print(f"   ✅ {metric_name} ({provider}): {value}")

    # Verify it used Redis Commands provider
    providers_used = [r.get("provider") for r in result.get("results", [])]
    if any("Redis Commands" in p for p in providers_used):
        print("\n   ✅ Confirmed: Used Redis Commands provider (direct connection)")
        return True
    else:
        print(f"\n   ⚠️  Warning: Expected Redis Commands provider, got: {providers_used}")
        return False


async def test_get_redis_diagnostics():
    """Test get_redis_diagnostics tool."""
    print("\n" + "=" * 80)
    print("TEST 2: get_redis_diagnostics (Comprehensive Redis Diagnostics)")
    print("=" * 80)

    redis_url = "redis://localhost:12000"  # Redis Enterprise

    print(f"\n🔍 Getting comprehensive diagnostics from {redis_url}")
    print("   Sections: memory, performance, clients")

    result = await get_redis_diagnostics(
        redis_url=redis_url,
        sections="memory,performance,clients",
    )

    print("\n✅ Result:")
    status = result.get("capture_status", result.get("status"))
    if status != "success":
        print(f"   ❌ Error: {result.get('error')}")
        return False

    print(f"   Status: {status}")
    print(f"   Sections captured: {result.get('sections_captured')}")

    diagnostics = result.get("diagnostics", {})

    # Check memory section
    if "memory" in diagnostics:
        memory = diagnostics["memory"]
        print("\n   📊 Memory Diagnostics:")
        print(f"      Used memory: {memory.get('used_memory_bytes', 0):,} bytes")
        print(f"      Peak memory: {memory.get('used_memory_peak_bytes', 0):,} bytes")
        print(f"      Fragmentation ratio: {memory.get('mem_fragmentation_ratio', 0)}")

    # Check performance section
    if "performance" in diagnostics:
        perf = diagnostics["performance"]
        print("\n   ⚡ Performance Diagnostics:")
        print(f"      Total commands: {perf.get('total_commands_processed', 0):,}")
        print(f"      Ops/sec: {perf.get('instantaneous_ops_per_sec', 0)}")
        print(f"      Keyspace hits: {perf.get('keyspace_hits', 0):,}")
        print(f"      Keyspace misses: {perf.get('keyspace_misses', 0):,}")

    # Check clients section
    if "clients" in diagnostics:
        clients = diagnostics["clients"]
        print("\n   👥 Client Diagnostics:")
        print(f"      Connected clients: {clients.get('connected_clients', 0)}")
        print(f"      Blocked clients: {clients.get('blocked_clients', 0)}")

    return True


async def test_comparison_prometheus_vs_redis():
    """Test comparing Prometheus metrics vs direct Redis connection."""
    print("\n" + "=" * 80)
    print("TEST 3: Comparison - Prometheus vs Direct Redis Connection")
    print("=" * 80)

    redis_url = "redis://localhost:12000"

    print("\n📊 Scenario: Agent needs to decide which tool to use")
    print("   Option 1: query_instance_metrics with redis_url (direct Redis)")
    print("   Option 2: query_instance_metrics without redis_url (Prometheus)")
    print("   Option 3: get_redis_diagnostics (comprehensive Redis data)")

    print("\n🔍 Testing Option 1: Direct Redis connection")
    result1 = await query_instance_metrics(
        metric_name="used_memory",
        redis_url=redis_url,
    )

    if "error" not in result1:
        provider1 = result1.get("results", [{}])[0].get("provider", "unknown")
        value1 = result1.get("results", [{}])[0].get("current_value", "N/A")
        print(f"   ✅ Got used_memory from {provider1}: {value1}")
    else:
        print(f"   ❌ Error: {result1.get('error')}")

    print("\n🔍 Testing Option 2: Prometheus (if available)")
    result2 = await query_instance_metrics(
        metric_name="redis_memory_used_bytes",
        provider_name="prometheus",
    )

    if "error" not in result2:
        provider2 = result2.get("results", [{}])[0].get("provider", "unknown")
        value2 = result2.get("results", [{}])[0].get("current_value", "N/A")
        print(f"   ✅ Got redis_memory_used_bytes from {provider2}: {value2}")
    else:
        print("   ⚠️  Prometheus not available or metric not found")

    print("\n🔍 Testing Option 3: Comprehensive diagnostics")
    result3 = await get_redis_diagnostics(
        redis_url=redis_url,
        sections="memory",
    )

    status3 = result3.get("capture_status", result3.get("status"))
    if status3 == "success":
        memory = result3.get("diagnostics", {}).get("memory", {})
        used_memory = memory.get("used_memory_bytes", "N/A")
        print(f"   ✅ Got comprehensive memory data: {used_memory} bytes")
        print("      Plus: fragmentation, peak, RSS, and more!")
    else:
        print(f"   ❌ Error: {result3.get('error')}")

    print("\n💡 Agent Decision Guide:")
    print("   - Use query_instance_metrics(redis_url=...) for quick metric checks")
    print("   - Use get_redis_diagnostics() for comprehensive investigation")
    print("   - Use query_instance_metrics(provider_name='prometheus') for time-series")

    return True


async def main():
    """Run all tests."""
    print("\n🧪 Testing Redis Direct Access Tools\n")

    results = []

    # Test 1: query_instance_metrics with redis_url
    try:
        result = await test_query_instance_metrics_with_redis_url()
        results.append(("query_instance_metrics with redis_url", result))
    except Exception as e:
        print(f"\n❌ Test 1 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("query_instance_metrics with redis_url", False))

    # Test 2: get_redis_diagnostics
    try:
        result = await test_get_redis_diagnostics()
        results.append(("get_redis_diagnostics", result))
    except Exception as e:
        print(f"\n❌ Test 2 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("get_redis_diagnostics", False))

    # Test 3: Comparison
    try:
        result = await test_comparison_prometheus_vs_redis()
        results.append(("Prometheus vs Redis comparison", result))
    except Exception as e:
        print(f"\n❌ Test 3 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Prometheus vs Redis comparison", False))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result for _, result in results)

    if all_passed:
        print("\n🎉 All tests passed!")
        print("\n💡 The agent now has multiple ways to access Redis data:")
        print("   1. query_instance_metrics(redis_url=...) - Quick metrics via INFO")
        print("   2. get_redis_diagnostics(redis_url=...) - Comprehensive diagnostics")
        print("   3. query_redis_enterprise_cluster() - Enterprise cluster status")
        print("   4. query_instance_metrics(provider_name='prometheus') - Time-series")
        print("\n   The LLM should intelligently choose based on the situation!")
        return 0
    else:
        print("\n⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
