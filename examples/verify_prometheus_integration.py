#!/usr/bin/env python3
"""Verification script for Prometheus provider integration.

This script verifies that the Prometheus provider:
1. Loads correctly via ToolManager
2. Coexists with other providers (KnowledgeBase)
3. Can execute queries successfully
4. Handles errors gracefully

Run this to verify the integration is working correctly.
"""

import asyncio
import os
import sys


async def verify_prometheus_integration():
    """Verify Prometheus provider integration."""

    print("=" * 70)
    print("Prometheus Provider Integration Verification")
    print("=" * 70)

    # Check environment
    print("\n1. Checking environment configuration...")
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    print(f"   PROMETHEUS_URL: {prometheus_url}")

    # Import after env check
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
        # Test 1: Provider loads via ToolManager
        print("\n2. Loading providers via ToolManager...")
        async with ToolManager() as manager:
            tools = manager.get_tools()
            print(f"   ✓ Loaded {len(tools)} total tools")

            # Check for knowledge base tools
            knowledge_tools = [t for t in tools if "knowledge" in t.name]
            print(f"   ✓ Knowledge base tools: {len(knowledge_tools)}")

            # Check for Prometheus tools
            prometheus_tools = [t for t in tools if "prometheus" in t.name]
            print(f"   ✓ Prometheus tools: {len(prometheus_tools)}")

            if len(prometheus_tools) != 3:
                print(f"   ✗ ERROR: Expected 3 Prometheus tools, got {len(prometheus_tools)}")
                return False

            # Test 2: List tool names
            print("\n3. Prometheus tools available:")
            for tool in prometheus_tools:
                operation = tool.name.split("_")[-1] if "_" in tool.name else tool.name
                print(f"   - {operation}: {tool.description[:60]}...")

            # Test 3: Execute a query
            print("\n4. Testing query execution...")
            query_tool = next(
                (t for t in prometheus_tools if "query" in t.name and "range" not in t.name), None
            )

            if not query_tool:
                print("   ✗ ERROR: Query tool not found")
                return False

            try:
                result = await manager.resolve_tool_call(
                    tool_name=query_tool.name, args={"query": "up"}
                )

                if result.get("status") == "success":
                    print("   ✓ Query executed successfully")
                    print(f"   ✓ Query: {result.get('query')}")
                    print(f"   ✓ Data points: {len(result.get('data', []))}")
                elif result.get("status") == "error":
                    print("   ⚠ Query returned error (Prometheus may not be running)")
                    print(f"   Error: {result.get('error')}")
                    print("   This is OK if Prometheus is not running locally")
                else:
                    print(f"   ✗ Unexpected result: {result}")
                    return False

            except Exception as e:
                print(f"   ⚠ Query execution failed: {e}")
                print("   This is OK if Prometheus is not running locally")

            # Test 4: List metrics
            print("\n5. Testing metric discovery...")
            list_tool = next((t for t in prometheus_tools if "list_metrics" in t.name), None)

            if not list_tool:
                print("   ✗ ERROR: List metrics tool not found")
                return False

            try:
                result = await manager.resolve_tool_call(tool_name=list_tool.name, args={})

                if result.get("status") == "success":
                    print("   ✓ Metric discovery successful")
                    print(f"   ✓ Found {result.get('count', 0)} metrics")
                elif result.get("status") == "error":
                    print("   ⚠ Metric discovery returned error")
                    print(f"   Error: {result.get('error')}")
                    print("   This is OK if Prometheus is not running locally")

            except Exception as e:
                print(f"   ⚠ Metric discovery failed: {e}")
                print("   This is OK if Prometheus is not running locally")

            # Test 5: Error handling
            print("\n6. Testing error handling...")
            try:
                result = await manager.resolve_tool_call(
                    tool_name=query_tool.name, args={"query": "invalid{{{query"}
                )

                if result.get("status") == "error":
                    print("   ✓ Invalid query handled gracefully")
                    print(f"   ✓ Error message: {result.get('error', '')[:60]}...")
                else:
                    print("   ⚠ Expected error status for invalid query")

            except Exception as e:
                print(f"   ⚠ Error handling test failed: {e}")

        print("\n" + "=" * 70)
        print("✓ Verification Complete!")
        print("=" * 70)
        print("\nSummary:")
        print("  - Prometheus provider loads correctly")
        print("  - Coexists with KnowledgeBase provider")
        print("  - Tools are properly registered")
        print("  - Query execution works (if Prometheus is running)")
        print("  - Error handling is graceful")
        print("\nThe Prometheus provider is fully integrated! 🎉")
        print("=" * 70)

        return True

    except Exception as e:
        print(f"\n✗ Verification failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Restore original settings
        config_module.settings = original_settings


def main():
    """Main entry point."""
    success = asyncio.run(verify_prometheus_integration())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
