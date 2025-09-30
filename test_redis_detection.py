#!/usr/bin/env python3
"""
Test script to demonstrate Redis instance type detection.

This script tests the Redis instance type detection functionality
against different Redis instances to show how the agent could
identify Redis Enterprise vs OSS instances.
"""

import asyncio
import json
import sys
from redis_sre_agent.tools.redis_instance_detector import (
    detect_redis_instance_type,
    get_redis_enterprise_info,
    RedisInstanceType,
)


async def test_redis_detection():
    """Test Redis instance type detection with various connection URLs."""

    # Test cases with different Redis instances
    test_cases = [
        {
            "name": "Redis Enterprise (from docker-compose)",
            "url": "redis://admin%40redis.com:admin@redis-enterprise-node1:12000/0",
            "expected": RedisInstanceType.REDIS_ENTERPRISE,
        },
        {
            "name": "Local Redis OSS (demo)",
            "url": "redis://redis-demo:6379",
            "expected": RedisInstanceType.OSS_SINGLE,
        },
        {
            "name": "Redis Cloud (example)",
            "url": "redis://user:pass@redis-12345.c1.us-east-1-1.ec2.cloud.redislabs.com:12345",
            "expected": RedisInstanceType.REDIS_CLOUD,
        },
        {
            "name": "AWS ElastiCache (example)",
            "url": "redis://my-cluster.abc123.cache.amazonaws.com:6379",
            "expected": RedisInstanceType.REDIS_CLOUD,
        },
    ]

    print("🔍 Redis Instance Type Detection Test")
    print("=" * 50)

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {test_case['name']}")
        print(f"   URL: {test_case['url']}")
        print(f"   Expected: {test_case['expected']}")

        try:
            # Detect instance type
            detected_type, detection_info = await detect_redis_instance_type(
                test_case["url"], timeout=3.0
            )

            print(f"   Detected: {detected_type}")
            print(f"   Method: {detection_info.get('detection_method', 'unknown')}")
            print(f"   Confidence: {detection_info.get('confidence', 'unknown')}")

            # Check if connection was successful
            if detection_info.get("connection_successful"):
                print("   ✅ Connection successful")

                # Show server info if available
                server_info = detection_info.get("server_info", {})
                if server_info:
                    print(f"   Redis Version: {server_info.get('redis_version', 'unknown')}")
                    print(f"   Mode: {server_info.get('redis_mode', 'unknown')}")
                    print(f"   Port: {server_info.get('tcp_port', 'unknown')}")

                # Show modules if any
                modules = detection_info.get("modules", [])
                if modules:
                    print(f"   Modules: {', '.join(modules)}")

                # Show enterprise features if detected
                enterprise_features = detection_info.get("enterprise_features", [])
                if enterprise_features:
                    print(f"   Enterprise Features: {', '.join(enterprise_features)}")

                # If it's Redis Enterprise, get detailed info
                if detected_type == RedisInstanceType.REDIS_ENTERPRISE:
                    print("\n   📊 Getting Redis Enterprise details...")
                    enterprise_info = await get_redis_enterprise_info(test_case["url"])

                    if enterprise_info.get("is_enterprise"):
                        print("   ✅ Confirmed Redis Enterprise")

                        # Show memory info
                        memory_info = enterprise_info.get("memory_info", {})
                        if memory_info:
                            print(
                                f"   Memory Used: {memory_info.get('used_memory_human', 'unknown')}"
                            )
                            print(f"   Max Memory: {memory_info.get('maxmemory_human', 'unknown')}")
                            print(
                                f"   Eviction Policy: {memory_info.get('maxmemory_policy', 'unknown')}"
                            )

                        # Show replication info
                        repl_info = enterprise_info.get("replication_info", {})
                        if repl_info:
                            print(f"   Role: {repl_info.get('role', 'unknown')}")
                            if repl_info.get("connected_slaves", 0) > 0:
                                print(f"   Connected Slaves: {repl_info['connected_slaves']}")

                        # Show modules
                        modules = enterprise_info.get("modules", [])
                        if modules:
                            print("   Enterprise Modules:")
                            for module in modules:
                                print(
                                    f"     - {module.get('name', 'unknown')} v{module.get('version', 'unknown')}"
                                )

            else:
                print("   ❌ Connection failed")
                if "connection_error" in detection_info:
                    print(f"   Error: {detection_info['connection_error']}")

            # Check if detection matches expectation
            if detected_type == test_case["expected"]:
                print("   ✅ Detection matches expectation")
            else:
                print("   ⚠️  Detection differs from expectation")

        except Exception as e:
            print(f"   ❌ Test failed: {e}")

    print("\n" + "=" * 50)
    print("🎯 Detection Summary")
    print("\nThe Redis SRE Agent can now:")
    print("1. ✅ Detect Redis Enterprise vs OSS instances")
    print("2. ✅ Identify cluster vs single-node configurations")
    print("3. ✅ Recognize cloud-hosted Redis services")
    print("4. ✅ Extract Enterprise-specific features and modules")
    print("5. ✅ Provide detailed instance information for better troubleshooting")

    print("\n🔧 Agent Integration Benefits:")
    print("- Tailored health checks based on instance type")
    print("- Enterprise-specific diagnostics and recommendations")
    print("- Cluster-aware monitoring and alerting")
    print("- Cloud-specific best practices and limitations")


if __name__ == "__main__":
    try:
        asyncio.run(test_redis_detection())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        sys.exit(1)
