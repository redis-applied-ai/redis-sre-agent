#!/usr/bin/env python3
"""
Script to identify and help fix instances with masked URLs in Redis.

This script will:
1. Load all instances from Redis
2. Identify instances with masked URLs (*********)
3. Print them out so you can fix them via the API or UI

Usage:
    python scripts/fix_masked_instance_urls.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client


async def check_instances():
    """Check for instances with masked URLs."""
    try:
        redis_client = get_redis_client()
        instances_data = await redis_client.get(RedisKeys.instances_set())

        if not instances_data:
            print("No instances found in Redis.")
            return

        instances_list = json.loads(instances_data)
        print(f"\nFound {len(instances_list)} instances in Redis\n")
        print("=" * 80)

        masked_count = 0
        for inst in instances_list:
            name = inst.get("name", "unknown")
            inst_id = inst.get("id", "unknown")
            conn_url = inst.get("connection_url", "")

            is_masked = conn_url == "**********" or conn_url.startswith("***")

            if is_masked:
                masked_count += 1
                print("\n❌ MASKED URL FOUND:")
                print(f"   Name: {name}")
                print(f"   ID: {inst_id}")
                print(f"   URL: {conn_url}")
                print(f"   Environment: {inst.get('environment', 'unknown')}")
                print(f"   Usage: {inst.get('usage', 'unknown')}")
            else:
                print("\n✅ Valid URL:")
                print(f"   Name: {name}")
                print(f"   ID: {inst_id}")
                print(
                    f"   URL: {conn_url[:30]}..." if len(conn_url) > 30 else f"   URL: {conn_url}"
                )

        print("\n" + "=" * 80)
        print("\nSummary:")
        print(f"  Total instances: {len(instances_list)}")
        print(f"  Instances with masked URLs: {masked_count}")
        print(f"  Instances with valid URLs: {len(instances_list) - masked_count}")

        if masked_count > 0:
            print(f"\n⚠️  WARNING: {masked_count} instance(s) have masked URLs!")
            print("   These instances cannot be used by the agent.")
            print("   Please update them via the UI or API with real connection URLs.")
            print("\n   Example API call to update:")
            print("   curl -X PUT http://localhost:8000/api/v1/instances/<instance_id> \\")
            print("     -H 'Content-Type: application/json' \\")
            print('     -d \'{"connection_url": "redis://your-real-host:6379"}\'')

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_instances())
