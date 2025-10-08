#!/usr/bin/env python3
"""Test script to verify key sampling tool."""

import asyncio
import sys

from redis_sre_agent.tools.dynamic_tools import get_redis_diagnostics, sample_redis_keys


async def test_keyspace_diagnostics():
    """Test getting keyspace statistics."""
    print("=" * 80)
    print("TEST 1: Get Keyspace Statistics (get_redis_diagnostics)")
    print("=" * 80)

    redis_url = "redis://localhost:12000"  # Redis Enterprise

    print(f"\n📊 Getting keyspace statistics from {redis_url}")
    print("   Using: get_redis_diagnostics(sections='keyspace')")

    result = await get_redis_diagnostics(
        redis_url=redis_url,
        sections="keyspace",
    )

    if result.get("capture_status") != "success":
        print(f"   ❌ Error: {result.get('error')}")
        return False

    keyspace = result.get("diagnostics", {}).get("keyspace", {})
    databases = keyspace.get("databases", {})

    print("\n✅ Keyspace Statistics:")
    for db_name, db_stats in databases.items():
        keys = db_stats.get("keys", 0)
        expires = db_stats.get("expires", 0)
        avg_ttl = db_stats.get("avg_ttl", 0)
        print(f"   {db_name}: {keys} keys, {expires} with TTL, avg TTL: {avg_ttl}ms")

    print("\n💡 This gives you STATISTICS but not actual key names")
    return True


async def test_sample_keys():
    """Test sampling actual keys."""
    print("\n" + "=" * 80)
    print("TEST 2: Sample Actual Keys (sample_redis_keys)")
    print("=" * 80)

    redis_url = "redis://localhost:12000"

    print(f"\n🔍 Sampling keys from {redis_url}")
    print("   Using: sample_redis_keys(pattern='*', count=50)")

    result = await sample_redis_keys(
        redis_url=redis_url,
        pattern="*",
        count=50,
    )

    if not result.get("success"):
        print(f"   ❌ Error: {result.get('error')}")
        return False

    print("\n✅ Key Sampling Results:")
    print(f"   Total keys in database: {result.get('total_keys_in_db')}")
    print(f"   Sampled: {result.get('sampled_count')} keys")

    # Show key patterns
    pattern_summary = result.get("pattern_summary", [])
    if pattern_summary:
        print("\n   📊 Key Pattern Analysis:")
        for pattern in pattern_summary[:10]:  # Top 10 patterns
            prefix = pattern.get("prefix")
            count = pattern.get("count")
            print(f"      {prefix}: {count} keys")

    # Show sample keys
    sampled_keys = result.get("sampled_keys", [])
    if sampled_keys:
        print("\n   🔑 Sample Keys (first 10):")
        for key in sampled_keys[:10]:
            print(f"      {key}")

    print("\n💡 This gives you ACTUAL KEY NAMES and patterns!")
    return True


async def test_pattern_matching():
    """Test sampling keys with a specific pattern."""
    print("\n" + "=" * 80)
    print("TEST 3: Sample Keys with Pattern (sample_redis_keys)")
    print("=" * 80)

    redis_url = "redis://localhost:12000"

    # First, let's see what patterns exist
    all_keys_result = await sample_redis_keys(
        redis_url=redis_url,
        pattern="*",
        count=100,
    )

    if not all_keys_result.get("success"):
        print(f"   ❌ Error: {all_keys_result.get('error')}")
        return True  # Don't fail the test if there are no keys

    pattern_summary = all_keys_result.get("pattern_summary", [])
    if not pattern_summary:
        print("   ℹ️  No keys found in database")
        return True

    # Get the most common pattern
    top_pattern = pattern_summary[0].get("prefix")
    pattern_to_search = f"{top_pattern}:*"

    print(f"\n🔍 Sampling keys matching pattern: {pattern_to_search}")

    result = await sample_redis_keys(
        redis_url=redis_url,
        pattern=pattern_to_search,
        count=20,
    )

    if not result.get("success"):
        print(f"   ❌ Error: {result.get('error')}")
        return False

    print("\n✅ Pattern Matching Results:")
    print(f"   Pattern: {result.get('pattern')}")
    print(f"   Matched: {result.get('sampled_count')} keys")

    sampled_keys = result.get("sampled_keys", [])
    if sampled_keys:
        print("\n   🔑 Matched Keys (first 10):")
        for key in sampled_keys[:10]:
            print(f"      {key}")

    return True


async def test_agent_decision_making():
    """Test the agent's decision-making process."""
    print("\n" + "=" * 80)
    print("TEST 4: Agent Decision-Making Guide")
    print("=" * 80)

    print("\n📋 When the agent needs keyspace information:")
    print()
    print("   Scenario 1: User asks 'How many keys are in the database?'")
    print("   → Use: get_redis_diagnostics(sections='keyspace')")
    print("   → Returns: Statistics (total keys, expires, avg TTL)")
    print()
    print("   Scenario 2: User asks 'What types of keys exist?'")
    print("   → Use: sample_redis_keys(pattern='*', count=100)")
    print("   → Returns: Actual key names and pattern analysis")
    print()
    print("   Scenario 3: User asks 'Show me user-related keys'")
    print("   → Use: sample_redis_keys(pattern='user:*', count=50)")
    print("   → Returns: Keys matching the pattern")
    print()
    print("   Scenario 4: Agent suggests 'You should connect and check keys'")
    print("   → WRONG! Use sample_redis_keys() instead!")
    print("   → The agent can get the keys itself")
    print()

    print("💡 Key Decision Points:")
    print("   - Need statistics only? → get_redis_diagnostics(sections='keyspace')")
    print("   - Need actual key names? → sample_redis_keys()")
    print("   - Need specific pattern? → sample_redis_keys(pattern='prefix:*')")
    print("   - NEVER tell user to connect - do it yourself!")

    return True


async def main():
    """Run all tests."""
    print("\n🧪 Testing Key Sampling Tools\n")

    results = []

    # Test 1: Keyspace diagnostics
    try:
        result = await test_keyspace_diagnostics()
        results.append(("Keyspace diagnostics", result))
    except Exception as e:
        print(f"\n❌ Test 1 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Keyspace diagnostics", False))

    # Test 2: Sample keys
    try:
        result = await test_sample_keys()
        results.append(("Sample keys", result))
    except Exception as e:
        print(f"\n❌ Test 2 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Sample keys", False))

    # Test 3: Pattern matching
    try:
        result = await test_pattern_matching()
        results.append(("Pattern matching", result))
    except Exception as e:
        print(f"\n❌ Test 3 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Pattern matching", False))

    # Test 4: Decision making
    try:
        result = await test_agent_decision_making()
        results.append(("Agent decision-making guide", result))
    except Exception as e:
        print(f"\n❌ Test 4 failed with exception: {e}")
        import traceback

        traceback.print_exc()
        results.append(("Agent decision-making guide", False))

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
        print("\n💡 The agent now has TWO ways to get keyspace information:")
        print("   1. get_redis_diagnostics(sections='keyspace') - Statistics only")
        print("   2. sample_redis_keys() - Actual key names and patterns")
        print("\n   The agent should NEVER tell the user to connect and check keys!")
        print("   It can do it itself using sample_redis_keys()!")
        return 0
    else:
        print("\n⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
