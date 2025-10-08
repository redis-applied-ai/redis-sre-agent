#!/usr/bin/env python3
"""Test script to verify provider architecture fixes."""

import asyncio
import sys

from redis_sre_agent.tools.registry import get_global_registry

from redis_sre_agent.tools.dynamic_tools import query_instance_metrics


async def test_redis_url_parameter():
    """Test that redis_url parameter works correctly."""
    print("=" * 80)
    print("TEST 1: Query Redis Enterprise with redis_url parameter")
    print("=" * 80)

    # Test querying Redis Enterprise instance
    redis_enterprise_url = "redis://localhost:12000"

    print(f"\n📊 Querying Redis Enterprise at {redis_enterprise_url}")
    print("   Metrics: used_memory, connected_clients")

    result = await query_instance_metrics(
        metric_names=["used_memory", "connected_clients"],
        redis_url=redis_enterprise_url,
    )

    print("\n✅ Result:")
    print(f"   Metrics queried: {result.get('metrics_queried', result.get('metric_name'))}")
    print(f"   Providers queried: {result.get('providers_queried')}")

    if "error" in result:
        print(f"   ❌ Error: {result['error']}")
        return False

    for metric_result in result.get("results", []):
        metric_name = metric_result.get("metric_name")
        if "error" in metric_result:
            print(f"   ⚠️  {metric_name}: {metric_result['error']}")
        else:
            value = metric_result.get("current_value")
            print(f"   ✅ {metric_name}: {value}")

    return True


async def test_batch_metrics():
    """Test that batch metrics queries work."""
    print("\n" + "=" * 80)
    print("TEST 2: Batch metrics query")
    print("=" * 80)

    redis_url = "redis://localhost:7843"  # Application Redis

    print(f"\n📊 Querying multiple metrics from {redis_url}")
    print("   Metrics: used_memory, connected_clients, total_commands_processed")

    result = await query_instance_metrics(
        metric_names=["used_memory", "connected_clients", "total_commands_processed"],
        redis_url=redis_url,
    )

    print("\n✅ Result:")
    print(f"   Metrics queried: {result.get('metrics_queried')}")
    print(f"   Providers queried: {result.get('providers_queried')}")

    if "error" in result:
        print(f"   ❌ Error: {result['error']}")
        return False

    for metric_result in result.get("results", []):
        metric_name = metric_result.get("metric_name")
        if "error" in metric_result:
            print(f"   ⚠️  {metric_name}: {metric_result['error']}")
        else:
            value = metric_result.get("current_value")
            print(f"   ✅ {metric_name}: {value}")

    return True


async def test_no_instance_bound_providers():
    """Test that no instance-bound Redis providers are registered at startup."""
    print("\n" + "=" * 80)
    print("TEST 3: Check provider registry")
    print("=" * 80)

    registry = get_global_registry()
    status = registry.get_registry_status()

    print("\n📋 Registry Status:")
    print(f"   Total providers: {status['total_providers']}")
    print(f"   Providers: {status['providers']}")
    print(f"   Capabilities: {status['capabilities_available']}")

    # Check if 'redis' provider is registered (it shouldn't be)
    if "redis" in status["providers"]:
        print("\n   ⚠️  WARNING: 'redis' provider is registered (should not be instance-bound)")
        redis_provider = registry.get_provider("redis")
        if redis_provider:
            print(f"   Provider name: {redis_provider.provider_name}")
        return False
    else:
        print("\n   ✅ No instance-bound 'redis' provider registered (correct!)")
        return True


async def main():
    """Run all tests."""
    print("\n🧪 Testing Provider Architecture Fixes\n")

    results = []

    # Test 1: redis_url parameter
    try:
        result = await test_redis_url_parameter()
        results.append(("redis_url parameter", result))
    except Exception as e:
        print(f"\n❌ Test 1 failed with exception: {e}")
        results.append(("redis_url parameter", False))

    # Test 2: batch metrics
    try:
        result = await test_batch_metrics()
        results.append(("batch metrics", result))
    except Exception as e:
        print(f"\n❌ Test 2 failed with exception: {e}")
        results.append(("batch metrics", False))

    # Test 3: no instance-bound providers
    try:
        result = await test_no_instance_bound_providers()
        results.append(("no instance-bound providers", result))
    except Exception as e:
        print(f"\n❌ Test 3 failed with exception: {e}")
        results.append(("no instance-bound providers", False))

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
        return 0
    else:
        print("\n⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
