#!/usr/bin/env python3
"""Test script to verify Redis Enterprise provider integration."""

import asyncio
import sys

from redis_sre_agent.tools.dynamic_tools import (
    query_redis_enterprise_cluster,
    query_redis_enterprise_databases,
    query_redis_enterprise_nodes,
)
from redis_sre_agent.tools.providers import create_redis_enterprise_provider


async def test_redis_enterprise_provider():
    """Test Redis Enterprise provider directly."""
    print("=" * 80)
    print("TEST 1: Redis Enterprise Provider - Direct Access")
    print("=" * 80)

    provider = create_redis_enterprise_provider(container_name="redis-enterprise-node1")

    print(f"\n📋 Provider: {provider.provider_name}")
    print(f"   Capabilities: {[c.value for c in provider.capabilities]}")

    # Test health check
    print("\n🏥 Health Check:")
    health = await provider.health_check()
    print(f"   Status: {health.get('status')}")
    print(f"   Cluster OK: {health.get('cluster_ok')}")

    # Test cluster status
    print("\n📊 Cluster Status:")
    cluster_status = await provider.get_cluster_status()
    if cluster_status.get("success"):
        summary = cluster_status.get("summary", {})
        print("   ✅ Success")
        print(f"   Node count: {summary.get('node_count')}")
        print(f"   Database count: {summary.get('database_count')}")
        print(f"   Cluster OK: {summary.get('cluster_ok')}")
    else:
        print(f"   ❌ Error: {cluster_status.get('error')}")
        return False

    # Test node status
    print("\n🖥️  Node Status:")
    node_status = await provider.get_node_status()
    if node_status.get("success"):
        summary = node_status.get("summary", {})
        print("   ✅ Success")
        print(f"   Total nodes: {summary.get('total_nodes')}")
        print(f"   Nodes in maintenance: {summary.get('maintenance_mode_nodes')}")

        # Show node details
        for node in summary.get("nodes", []):
            node_id = node.get("node_id")
            shards = node.get("shards")
            in_maint = node.get("in_maintenance")
            status = "🔧 MAINTENANCE" if in_maint else "✅ OK"
            print(f"   Node {node_id}: {shards} shards - {status}")
    else:
        print(f"   ❌ Error: {node_status.get('error')}")
        return False

    # Test database status
    print("\n💾 Database Status:")
    db_status = await provider.get_database_status()
    if db_status.get("success"):
        summary = db_status.get("summary", {})
        print("   ✅ Success")
        print(f"   Total databases: {summary.get('total_databases')}")
    else:
        print(f"   ❌ Error: {db_status.get('error')}")
        return False

    return True


async def test_redis_enterprise_tools():
    """Test Redis Enterprise tools (dynamic tools interface)."""
    print("\n" + "=" * 80)
    print("TEST 2: Redis Enterprise Tools - Dynamic Tools Interface")
    print("=" * 80)

    # Test cluster query
    print("\n📊 Query Cluster:")
    result = await query_redis_enterprise_cluster()
    if result.get("success"):
        print("   ✅ Success")
        summary = result.get("summary", {})
        print(f"   Node count: {summary.get('node_count')}")
        print(f"   Database count: {summary.get('database_count')}")
    else:
        print(f"   ❌ Error: {result.get('error')}")
        return False

    # Test node query
    print("\n🖥️  Query Nodes:")
    result = await query_redis_enterprise_nodes()
    if result.get("success"):
        print("   ✅ Success")
        summary = result.get("summary", {})
        maintenance_nodes = summary.get("maintenance_mode_nodes", [])
        if maintenance_nodes:
            print(f"   ⚠️  Nodes in maintenance mode: {maintenance_nodes}")
        else:
            print("   ✅ No nodes in maintenance mode")
    else:
        print(f"   ❌ Error: {result.get('error')}")
        return False

    # Test database query
    print("\n💾 Query Databases:")
    result = await query_redis_enterprise_databases()
    if result.get("success"):
        print("   ✅ Success")
        summary = result.get("summary", {})
        print(f"   Total databases: {summary.get('total_databases')}")
    else:
        print(f"   ❌ Error: {result.get('error')}")
        return False

    return True


async def test_maintenance_mode_detection():
    """Test that maintenance mode is correctly detected."""
    print("\n" + "=" * 80)
    print("TEST 3: Maintenance Mode Detection")
    print("=" * 80)

    print("\n🔍 Checking for nodes in maintenance mode...")

    result = await query_redis_enterprise_nodes()

    if not result.get("success"):
        print(f"   ❌ Error: {result.get('error')}")
        return False

    summary = result.get("summary", {})
    maintenance_nodes = summary.get("maintenance_mode_nodes", [])
    all_nodes = summary.get("nodes", [])

    print("\n📊 Node Status:")
    for node in all_nodes:
        node_id = node.get("node_id")
        shards = node.get("shards")
        in_maint = node.get("in_maintenance")

        if in_maint:
            print(f"   🔧 Node {node_id}: {shards} - IN MAINTENANCE MODE")
        else:
            print(f"   ✅ Node {node_id}: {shards} - OK")

    if maintenance_nodes:
        print(
            f"\n⚠️  Found {len(maintenance_nodes)} node(s) in maintenance mode: {maintenance_nodes}"
        )
        print("   ✅ Maintenance mode detection working correctly!")
    else:
        print("\n✅ No nodes in maintenance mode")
        print("   💡 To test maintenance mode detection, run:")
        print("      docker exec redis-enterprise-node1 rladmin node 2 maintenance_mode on")

    return True


async def main():
    """Run all tests."""
    print("\n🧪 Testing Redis Enterprise Provider Integration\n")

    results = []

    # Test 1: Provider direct access
    try:
        result = await test_redis_enterprise_provider()
        results.append(("Redis Enterprise Provider", result))
    except Exception as e:
        print(f"\n❌ Test 1 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Redis Enterprise Provider", False))

    # Test 2: Dynamic tools interface
    try:
        result = await test_redis_enterprise_tools()
        results.append(("Redis Enterprise Tools", result))
    except Exception as e:
        print(f"\n❌ Test 2 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Redis Enterprise Tools", False))

    # Test 3: Maintenance mode detection
    try:
        result = await test_maintenance_mode_detection()
        results.append(("Maintenance Mode Detection", result))
    except Exception as e:
        print(f"\n❌ Test 3 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Maintenance Mode Detection", False))

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
        print("\n💡 Redis Enterprise tools are now integrated into the provider system!")
        print("   The agent can use these tools:")
        print("   - query_redis_enterprise_cluster()")
        print("   - query_redis_enterprise_nodes()")
        print("   - query_redis_enterprise_databases()")
        return 0
    else:
        print("\n⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
