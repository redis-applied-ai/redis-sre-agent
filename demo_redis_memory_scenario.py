#!/usr/bin/env python3
"""
Demo script for Redis SRE Agent - Memory Pressure Scenario

This script demonstrates:
1. Setting up Redis with low memory limits
2. Loading Redis with data to trigger memory pressure
3. Using the SRE agent to detect and diagnose the issue
4. Showing agent recommendations for resolution

Usage:
    python demo_redis_memory_scenario.py
"""

import asyncio
import time
import redis
import os
from pathlib import Path

from redis_sre_agent.tools.redis_diagnostics import RedisDiagnostics
from redis_sre_agent.agent.langgraph_agent import get_sre_agent


async def main():
    """Run the complete Redis memory pressure demo."""
    
    print("🚀 Redis SRE Agent - Memory Pressure Demo")
    print("=" * 50)
    
    # Check if Redis is available - try different ports
    redis_ports = [7942, 6379]  # Try low-memory test port first, then default
    redis_client = None
    redis_port = None
    
    for port in redis_ports:
        try:
            redis_client = redis.Redis(host="localhost", port=port, decode_responses=True)
            redis_client.ping()
            redis_port = port
            print(f"✅ Redis connection established on port {port}")
            break
        except redis.ConnectionError:
            continue
    
    if redis_client is None:
        print("❌ Redis not available on any port. Please start Redis first:")
        print("   For low memory demo: docker-compose -f docker-compose.yml -f docker-compose.test.yml up redis -d")
        print("   For regular demo: docker-compose up redis -d")
        return
    
    # Step 1: Check initial Redis state
    print("\n📊 Step 1: Checking initial Redis state...")
    
    health_checker = RedisDiagnostics(f"redis://localhost:{redis_port}/0")
    
    # Get baseline memory info
    initial_info = redis_client.info("memory")
    initial_memory = initial_info.get("used_memory", 0)
    maxmemory = initial_info.get("maxmemory", 0)
    
    print(f"   Initial memory usage: {initial_memory / (1024*1024):.2f} MB")
    if maxmemory > 0:
        print(f"   Memory limit (maxmemory): {maxmemory / (1024*1024):.2f} MB")
        print(f"   Memory utilization: {(initial_memory / maxmemory * 100):.1f}%")
    else:
        print("   No memory limit set (maxmemory: 0)")
    
    # Step 2: Load Redis with data to simulate memory pressure
    print("\n📈 Step 2: Loading Redis with data to simulate memory pressure...")
    
    # Clear any existing demo keys first
    existing_keys = redis_client.keys("demo:memory:*")
    if existing_keys:
        redis_client.delete(*existing_keys)
        print(f"   Cleared {len(existing_keys)} existing demo keys")
    
    # Load data in batches
    batch_size = 100
    total_keys = 800  # Adjust based on memory limit
    key_size = 8192   # 8KB per key
    
    print(f"   Loading {total_keys} keys of {key_size} bytes each...")
    
    for batch in range(0, total_keys, batch_size):
        pipe = redis_client.pipeline()
        for i in range(batch, min(batch + batch_size, total_keys)):
            key = f"demo:memory:key:{i:04d}"
            # Create data that will consume memory
            value = f"data:{i}:{'x' * (key_size - 20)}"
            pipe.set(key, value)
        
        pipe.execute()
        
        # Show progress
        progress = min(batch + batch_size, total_keys)
        print(f"   Progress: {progress}/{total_keys} keys loaded")
        
        # Brief pause to not overwhelm Redis
        if batch % 200 == 0:
            time.sleep(0.1)
    
    # Wait for Redis to update memory stats
    time.sleep(2)
    
    # Step 3: Check memory state after loading
    print("\n📊 Step 3: Checking Redis state after data loading...")
    
    after_info = redis_client.info("memory")
    after_memory = after_info.get("used_memory", 0)
    
    print(f"   Memory usage after loading: {after_memory / (1024*1024):.2f} MB")
    print(f"   Memory increase: {(after_memory - initial_memory) / (1024*1024):.2f} MB")
    
    if maxmemory > 0:
        utilization = (after_memory / maxmemory * 100)
        print(f"   Memory utilization: {utilization:.1f}%")
        
        if utilization > 80:
            print("   🚨 HIGH MEMORY USAGE DETECTED!")
        elif utilization > 60:
            print("   ⚠️  ELEVATED MEMORY USAGE")
    
    # Step 4: Run SRE agent diagnostics
    print("\n🔍 Step 4: Running SRE agent health diagnostics...")
    
    diagnostics = await health_checker.run_diagnostic_suite()
    
    # Display key diagnostic results
    diagnostic_data = diagnostics.get("diagnostics", {})
    memory_diag = diagnostic_data.get("memory", {})
    memory_status = memory_diag.get("status", "unknown")
    
    print(f"   Memory health status: {memory_status}")
    print(f"   Used memory: {memory_diag.get('used_memory_bytes', 0) / (1024*1024):.2f} MB")
    
    if 'memory_usage_percentage' in memory_diag:
        print(f"   Memory utilization: {memory_diag['memory_usage_percentage']:.1f}%")
    
    # Check keyspace
    keyspace_diag = diagnostic_data.get("keyspace", {})
    total_keys = keyspace_diag.get("total_keys", 0)
    
    print(f"   Total keys: {total_keys}")
    
    # Overall status
    overall_status = diagnostics.get("overall_status", "unknown")
    print(f"   Overall Redis health: {overall_status}")
    
    # Step 5: Query SRE agent for guidance
    print("\n🤖 Step 5: Querying SRE agent for guidance...")
    
    # Use a query that prompts the agent to actively investigate
    query = "I'm monitoring a Redis instance and see concerning behavior. Please investigate the issue and tell me what you found."
    
    try:
        print("   Consulting SRE agent...")
        agent = get_sre_agent()
        
        response = await agent.process_query(
            query=query.strip(),
            session_id="demo_memory_scenario",
            user_id="sre_demo_user"
        )
        
        print("\n📋 SRE Agent Recommendations:")
        print("-" * 40)
        print(response)
        
    except Exception as e:
        print(f"   ⚠️  Agent query failed: {str(e)}")
        print("   This might be due to missing OpenAI API key or network issues.")
        
        # Provide fallback guidance
        print("\n📋 Fallback Recommendations:")
        print("-" * 40)
        if maxmemory == 0:
            print("1. Set memory limit: CONFIG SET maxmemory 50mb")
            print("2. Set eviction policy: CONFIG SET maxmemory-policy allkeys-lru")
        else:
            print("1. Check which keys are using the most memory:")
            print("   redis-cli --bigkeys")
            print("2. Consider optimizing data structures or expiring old keys")
        
        print("3. Monitor memory fragmentation in INFO memory")
        print("4. Set up memory usage alerts")
    
    # Step 6: Cleanup and summary
    print("\n🧹 Step 6: Cleanup and summary...")
    
    # Clean up demo keys
    demo_keys = redis_client.keys("demo:memory:*")
    if demo_keys:
        redis_client.delete(*demo_keys)
        print(f"   Cleaned up {len(demo_keys)} demo keys")
    
    # Final memory check
    final_info = redis_client.info("memory")
    final_memory = final_info.get("used_memory", 0)
    
    print(f"   Final memory usage: {final_memory / (1024*1024):.2f} MB")
    
    print("\n✅ Demo completed!")
    print("\n💡 To run this demo with low memory limits:")
    print("   docker-compose -f docker-compose.yml -f docker-compose.test.yml up redis -d")
    print("   (This uses redis-low-memory.conf with 10MB limit)")


if __name__ == "__main__":
    # Ensure we have the required environment
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Agent queries may fail.")
        print("   Set this environment variable to enable full agent functionality.")
        print()
    
    asyncio.run(main())