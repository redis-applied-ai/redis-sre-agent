#!/usr/bin/env python3
"""
Redis SRE Agent - Interactive Demo

This comprehensive demo showcases the Redis SRE Agent's capabilities across multiple scenarios:
1. Memory Pressure Analysis - Load Redis and diagnose memory issues
2. Connection Issues Simulation - Simulate and resolve connection problems
3. Performance Degradation - Analyze slow operations and optimization
4. Full Health Check - Complete diagnostic suite with agent consultation

Usage:
    python demo_redis_memory_scenario.py [--scenario <name>] [--auto-run]

Options:
    --scenario: Run specific scenario (memory, connections, performance, health)
    --auto-run: Run all scenarios automatically without user input
"""

import argparse
import asyncio
import logging
import os
import random
import time
import warnings
from typing import Optional

import redis

from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.tools.redis_diagnostics import get_redis_diagnostics
from redis_sre_agent.tools.sre_functions import get_detailed_redis_diagnostics

DEMO_PORT = 7844

# TODO: Suppress Pydantic protected namespace warning from dependencies
warnings.filterwarnings(
    "ignore",
    message=r"Field \"model_name\" in .* has conflict with protected namespace \"model_\"",
    category=UserWarning,
)


class RedisSREDemo:
    """Interactive Redis SRE Agent demonstration."""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.redis_port: Optional[int] = None
        self.redis_url: Optional[str] = None
        self.scenarios = {
            "memory": self.memory_pressure_scenario,
            "connections": self.connection_issues_scenario,
            "performance": self.performance_scenario,
            "health": self.full_health_check,
        }
        self._setup_demo_logging()

    def _setup_demo_logging(self):
        """Configure logging for demo to reduce noise."""
        # Set agent and tool logging to WARNING to reduce noise during demo
        logging.getLogger("redis_sre_agent.agent").setLevel(logging.WARNING)
        logging.getLogger("redis_sre_agent.tools").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        # Keep only error/critical logs for demo experience
        demo_loggers = [
            "redis_sre_agent.agent.langgraph_agent",
            "redis_sre_agent.tools.sre_functions",
            "redis_sre_agent.tools.redis_diagnostics",
            "redis_sre_agent.tools.prometheus_client",
        ]

        for logger_name in demo_loggers:
            logging.getLogger(logger_name).setLevel(logging.ERROR)

    def print_header(self, title: str, symbol: str = "="):
        """Print a formatted header."""
        if symbol == "🧠":
            # Fix the repetitive emoji issue - use reasonable number
            print(f"\n{'=' * 15} 🧠 {title} 🧠 {'=' * 15}")
        elif symbol == "🔗":
            print(f"\n{'=' * 15} 🔗 {title} 🔗 {'=' * 15}")
        elif symbol == "⚡":
            print(f"\n{'=' * 15} ⚡ {title} ⚡ {'=' * 15}")
        elif symbol == "🏥":
            print(f"\n{'=' * 15} 🏥 {title} 🏥 {'=' * 15}")
        else:
            print(f"\n{symbol * 60}")
            print(f"🚀 {title}")
            print(f"{symbol * 60}")

    def print_step(self, step_num: int, description: str):
        """Print a formatted step."""
        print(f"\n📋 Step {step_num}: {description}")
        print("-" * 50)

    async def setup_redis_connection(self) -> bool:
        """Establish Redis connection and setup health checker."""
        # Use separate Redis instance for demo scenarios to avoid interference with agent operational data

        # Connect to separate Redis instance for demo scenarios
        self.redis_client = redis.Redis(host="localhost", port=DEMO_PORT, decode_responses=True)
        self.redis_client.ping()
        self.redis_port = DEMO_PORT
        self.redis_url = f"redis://localhost:{DEMO_PORT}/0"

        # Clear any existing data from previous demo runs to ensure clean state
        try:
            self.redis_client.flushdb()
            print(
                f"✅ Redis connection established on port {DEMO_PORT} (database cleared for clean demo)"
            )
        except redis.ConnectionError:
            print(f"❌ Redis connection failed on port {DEMO_PORT}")
            return False

        return True

    def show_main_menu(self) -> str:
        """Display main menu and get user selection."""
        self.print_header("Redis SRE Agent - Interactive Demo")
        print("\nAvailable scenarios:")
        print("1. 🧠 Memory Pressure Analysis - Simulate and diagnose memory issues")
        print("2. 🔗 Connection Issues - Analyze connection limits and timeouts")
        print("3. ⚡ Performance Analysis - Detect slow operations and bottlenecks")
        print("4. 🏥 Full Health Check - Complete diagnostic with agent consultation")
        print("5. 🚀 Run All Scenarios - Complete demonstration")
        print("0. 🚪 Exit")

        while True:
            try:
                choice = input("\nSelect scenario (0-5): ").strip()
                if choice in ["0", "1", "2", "3", "4", "5"]:
                    return choice
                else:
                    print("❌ Invalid choice, please select 0-5")
            except KeyboardInterrupt:
                print("\n👋 Demo interrupted by user")
                return "0"

    async def memory_pressure_scenario(self):
        """Run memory pressure analysis scenario."""
        self.print_header("Memory Pressure Analysis Scenario", "🧠")

        # Get baseline memory info
        initial_info = self.redis_client.info("memory")
        initial_memory = initial_info.get("used_memory", 0)
        maxmemory = initial_info.get("maxmemory", 0)

        self.print_step(1, "Setting up memory pressure scenario")

        # Set a memory limit to create realistic pressure scenario
        # Target: Create 80-90% memory utilization for demonstration
        target_memory_mb = 50  # 50MB limit for demo
        target_memory_bytes = target_memory_mb * 1024 * 1024

        print(f"   Initial memory usage: {initial_memory / (1024 * 1024):.2f} MB")
        print(f"   Setting maxmemory to {target_memory_mb} MB to create pressure scenario...")

        # Configure Redis for memory pressure scenario
        # Create a dangerous scenario: high memory usage with no eviction policy
        self.redis_client.config_set("maxmemory", str(target_memory_bytes))
        self.redis_client.config_set(
            "maxmemory-policy", "noeviction"
        )  # No eviction = potential OOM!

        # Verify the configuration was set
        updated_info = self.redis_client.info("memory")
        maxmemory = updated_info.get("maxmemory", 0)
        print(f"   Memory limit set to: {maxmemory / (1024 * 1024):.2f} MB")
        print(f"   Current utilization: {(initial_memory / maxmemory * 100):.1f}%")

        self.print_step(2, "Loading data to approach memory limit")

        # Clear any existing demo keys first
        existing_keys = []
        for pattern in ["user:profile:*", "product:details:*", "order:data:*"]:
            existing_keys.extend(self.redis_client.keys(pattern))
        if existing_keys:
            self.redis_client.delete(*existing_keys)
            print(f"   Cleared {len(existing_keys)} existing demo keys")

        # Get current memory usage after clearing keys
        current_info = self.redis_client.info("memory")
        current_memory = current_info.get("used_memory", 0)

        # Calculate data size to create memory pressure (target ~85% utilization)
        target_utilization = 0.85  # 85% utilization
        target_total_memory = int(maxmemory * target_utilization)
        target_data_size = target_total_memory - current_memory

        key_size = 8192  # 8KB per key
        estimated_keys = max(100, target_data_size // key_size)  # At least 100 keys

        print(f"   Target data size: {target_data_size / (1024 * 1024):.2f} MB")
        print(f"   Loading approximately {estimated_keys} keys to create memory pressure...")

        # Load data in batches and monitor memory usage
        batch_size = 50
        keys_loaded = 0

        for batch_start in range(0, estimated_keys, batch_size):
            batch_end = min(batch_start + batch_size, estimated_keys)
            pipe = self.redis_client.pipeline()

            for i in range(batch_start, batch_end):
                # Create realistic key patterns that look like persistent application data
                if i % 3 == 0:
                    key = f"user:profile:{i:04d}"
                elif i % 3 == 1:
                    key = f"product:details:{i:04d}"
                else:
                    key = f"order:data:{i:04d}"
                value = f"data:{i}:{'x' * (key_size - 20)}"
                pipe.set(key, value)  # No TTL = permanent data

            try:
                pipe.execute()
                keys_loaded = batch_end

                # Check memory usage after each batch
                current_info = self.redis_client.info("memory")
                current_memory = current_info.get("used_memory", 0)
                current_utilization = current_memory / maxmemory * 100

                print(
                    f"   Progress: {keys_loaded}/{estimated_keys} keys, Memory: {current_memory / (1024 * 1024):.1f}MB ({current_utilization:.1f}%)"
                )

                # Stop if we're approaching the limit to avoid evictions during loading
                if current_utilization > 80:
                    print(
                        f"   ⚠️  Approaching memory limit ({current_utilization:.1f}%), stopping data load"
                    )
                    break

            except Exception as e:
                print(f"   ⚠️  Memory pressure detected during loading: {str(e)}")
                break

            time.sleep(0.1)  # Brief pause between batches

        time.sleep(2)  # Wait for Redis to update memory stats

        self.print_step(3, "Analyzing memory pressure situation")
        final_info = self.redis_client.info("memory")
        final_memory = final_info.get("used_memory", 0)
        maxmemory = final_info.get("maxmemory", 0)  # Re-fetch in case it changed

        utilization = (final_memory / maxmemory * 100) if maxmemory > 0 else 0

        print(f"   Final memory usage: {final_memory / (1024 * 1024):.2f} MB")
        print(f"   Memory limit: {maxmemory / (1024 * 1024):.2f} MB")
        print(f"   Memory utilization: {utilization:.1f}%")
        print(f"   Keys successfully loaded: {keys_loaded}")

        # Check for evictions
        evicted_keys = final_info.get("evicted_keys", 0)
        if evicted_keys > 0:
            print(f"   🚨 EVICTIONS DETECTED: {evicted_keys} keys evicted")

        # Get fresh diagnostic data using the agent's diagnostic tool
        print("   Getting current Redis diagnostic data to send to agent...")
        diagnostics = await get_detailed_redis_diagnostics(self.redis_url)

        # Add key pattern analysis by sampling some keys
        print("   Sampling keys for pattern analysis...")
        sample_keys = []
        for pattern in ["user:profile:*", "product:details:*", "order:data:*"]:
            pattern_keys = self.redis_client.keys(pattern)
            if pattern_keys:
                # Sample up to 5 keys per pattern
                sample_keys.extend(pattern_keys[:5])

        # Add sample keys to diagnostic data
        if sample_keys:
            diagnostics.setdefault("diagnostics", {})["sample_keys"] = [
                key.decode() if isinstance(key, bytes) else key for key in sample_keys[:15]
            ]

        # Log current memory state for debugging
        current_info = self.redis_client.info("memory")
        current_memory = current_info.get("used_memory", 0)
        current_maxmemory = current_info.get("maxmemory", 0)
        print(
            f"   Debug - Current memory: {current_memory / (1024 * 1024):.2f} MB, maxmemory: {current_maxmemory / (1024 * 1024):.2f} MB"
        )

        # Format the diagnostics for the agent
        diagnostic_summary = self._format_diagnostics_for_agent(diagnostics)
        print(f"   Debug - Sample keys included: {len(sample_keys)} keys")
        if sample_keys:
            print(f"   Debug - Sample key patterns: {sample_keys[:5]}")

        # Debug: Check if diagnostic summary includes the investigation prompt
        if "INVESTIGATION REQUIRED" in diagnostic_summary:
            print("   Debug - Investigation prompt included in diagnostic data")

        # Consult agent with pre-loaded diagnostic data
        await self._run_agent_with_diagnostics(
            query="The application team has reported performance issues with this Redis instance. Please analyze the diagnostic data and provide immediate remediation steps.",
            diagnostic_data=diagnostic_summary,
        )

        # Cleanup and restore settings
        self.print_step(5, "Cleaning up and restoring settings")
        demo_keys = []
        for pattern in ["user:profile:*", "product:details:*", "order:data:*"]:
            demo_keys.extend(self.redis_client.keys(pattern))
        if demo_keys:
            self.redis_client.delete(*demo_keys)
            print(f"   Cleaned up {len(demo_keys)} demo keys")

        # Restore original maxmemory setting (0 = unlimited)
        self.redis_client.config_set("maxmemory", "0")
        self.redis_client.config_set("maxmemory-policy", "noeviction")
        print("   Restored original Redis memory settings")

        restored_info = self.redis_client.info("memory")
        restored_memory = restored_info.get("used_memory", 0)
        print(f"   Final memory usage: {restored_memory / (1024 * 1024):.2f} MB (unlimited)")

    async def connection_issues_scenario(self):
        """Simulate connection issues and demonstrate troubleshooting."""
        self.print_header("Connection Issues Analysis Scenario", "🔗")

        self.print_step(1, "Establishing clean baseline connection state")

        # Ensure we're starting with a clean slate
        self.redis_client.flushdb()

        # Get baseline connection info (should be just our demo connection)
        baseline_info = self.redis_client.info("clients")
        baseline_clients = baseline_info.get("connected_clients", 0)

        # Get original maxclients setting
        try:
            maxclients_result = self.redis_client.config_get("maxclients")
            original_maxclients = int(maxclients_result.get("maxclients", 10000))
        except Exception:
            original_maxclients = 10000

        print(f"   Baseline connected clients: {baseline_clients} (should be 1-2 for clean demo)")
        print(f"   Original maximum clients: {original_maxclients}")

        # Verify we have a clean environment
        if baseline_clients > 3:
            print(f"   ⚠️  Warning: {baseline_clients} existing connections detected")
            print("   This may indicate a shared Redis instance - results may be affected")

        self.print_step(2, "Creating connection pressure scenario")

        # Set a low connection limit to create a realistic demo scenario
        # This simulates a constrained environment or misconfiguration
        demo_maxclients = 25  # Very low limit to ensure we can hit it with demo connections

        print(f"   Setting maxclients to {demo_maxclients} for connection pressure demo...")
        self.redis_client.config_set("maxclients", str(demo_maxclients))

        # Verify the setting was applied
        updated_result = self.redis_client.config_get("maxclients")
        current_maxclients = int(updated_result.get("maxclients", demo_maxclients))
        print(f"   Connection limit reduced to: {current_maxclients}")
        print(f"   Current utilization: {(baseline_clients / current_maxclients * 100):.1f}%")

        self.print_step(3, "Simulating connection pressure and creating blocked clients")

        # Create connections that will approach the limit
        test_connections = []
        # Target 90% of the connection limit, accounting for baseline
        target_total_clients = int(current_maxclients * 0.9)
        target_new_connections = target_total_clients - baseline_clients
        target_new_connections = max(
            15, min(target_new_connections, current_maxclients - baseline_clients - 2)
        )

        print(f"   Attempting to create {target_new_connections} concurrent connections...")
        print(
            f"   Target total clients: {target_total_clients} (~90% of {current_maxclients} limit)"
        )
        print("   This should create clear connection pressure metrics...")

        connection_errors = 0
        successful_connections = 0

        try:
            for i in range(target_new_connections):
                try:
                    conn = redis.Redis(
                        host="localhost",
                        port=self.redis_port,
                        decode_responses=True,
                        socket_connect_timeout=2,  # Short timeout to detect connection issues
                        socket_timeout=2,
                    )
                    conn.ping()  # Ensure connection is established
                    test_connections.append(conn)
                    successful_connections += 1

                    if (i + 1) % 15 == 0 or i == target_new_connections - 1:
                        print(
                            f"   Progress: {i + 1}/{target_new_connections} connections attempted..."
                        )

                    # Add some delay to simulate realistic connection patterns
                    time.sleep(0.05)

                except redis.ConnectionError as e:
                    connection_errors += 1
                    if connection_errors == 1:
                        print(f"   ⚠️  Connection rejected: {str(e)}")
                        print("   This indicates we're hitting Redis connection limits!")
                    break  # Stop trying once we hit the limit
                except Exception as e:
                    connection_errors += 1
                    if connection_errors <= 3:  # Don't spam errors
                        print(f"   ❌ Connection error: {str(e)}")

            # Check connection state after simulation
            time.sleep(1)
            clients_info_after = self.redis_client.info("clients")
            clients_after = clients_info_after.get("connected_clients", 0)

            print(f"   ✅ Successfully created: {successful_connections} connections")
            print(f"   ❌ Connection errors: {connection_errors}")
            print(f"   📊 Total connected clients: {clients_after}")
            print(
                f"   📈 Connection utilization: {(clients_after / current_maxclients * 100):.1f}%"
            )

            # Create blocked client scenario using BLPOP operations
            print("   🧪 Creating blocked clients to demonstrate client queue issues...")
            blocked_clients_created = 0

            # Use some of the existing connections to create blocking operations
            for i in range(min(10, len(test_connections))):
                try:
                    conn = test_connections[i]
                    # Start BLPOP operations on non-existent keys (will block indefinitely)
                    # Use asyncio to run these in background without blocking the demo
                    import threading

                    def blocking_operation(connection, key_name):
                        try:
                            # This will block until timeout or key appears
                            connection.blpop([key_name], timeout=30)
                        except Exception:
                            pass  # Expected timeout or connection error

                    thread = threading.Thread(
                        target=blocking_operation, args=(conn, f"nonexistent_blocking_key_{i}")
                    )
                    thread.daemon = True
                    thread.start()
                    blocked_clients_created += 1
                    time.sleep(0.1)  # Brief delay between blocking operations
                except Exception as e:
                    print(f"   Warning: Could not create blocking operation: {e}")
                    break

            # Wait for blocked clients to register
            time.sleep(2)

            # Check for blocked clients in metrics
            final_clients_info = self.redis_client.info("clients")
            blocked_clients = final_clients_info.get("blocked_clients", 0)
            total_clients = final_clients_info.get("connected_clients", 0)

            print(f"   📋 Blocked clients created: {blocked_clients_created}")
            print(f"   📊 Redis reports blocked clients: {blocked_clients}")
            print(f"   📊 Total connected clients: {total_clients}")

            if blocked_clients > 0:
                print("   🚨 BLOCKED CLIENTS DETECTED - This indicates client queue issues!")

            utilization = (
                (total_clients / current_maxclients * 100) if current_maxclients > 0 else 0
            )

            if utilization > 90:
                print("   🚨 CRITICAL: Connection exhaustion imminent!")
            elif utilization > 80:
                print("   🚨 HIGH CONNECTION USAGE DETECTED!")
            elif utilization > 60:
                print("   ⚠️  ELEVATED CONNECTION USAGE")

            # Force additional connection attempts to generate rejection metrics
            print("   🧪 Testing connection rejection behavior...")
            extra_attempts = 8
            rejected_attempts = 0
            rejection_errors = []

            for i in range(extra_attempts):
                try:
                    extra_conn = redis.Redis(
                        host="localhost",
                        port=self.redis_port,
                        socket_connect_timeout=1,
                        socket_timeout=1,
                    )
                    extra_conn.ping()
                    test_connections.append(extra_conn)
                except redis.ConnectionError as e:
                    rejected_attempts += 1
                    rejection_errors.append(str(e))
                except Exception as e:
                    rejected_attempts += 1
                    rejection_errors.append(f"Connection error: {str(e)}")

            if rejected_attempts > 0:
                print(f"   🚨 {rejected_attempts}/{extra_attempts} connection attempts rejected!")
                print("   📊 This creates visible connection_rejected_* metrics in Redis")

            # Get comprehensive diagnostics showing connection problems
            print("   📊 Getting diagnostic data to show connection issues...")
            _ = await get_detailed_redis_diagnostics(self.redis_url)

            # Run diagnostics and agent consultation with connection-focused query
            await self._run_diagnostics_and_agent_query(
                f"Application users are reporting connection timeouts and service unavailability. Current metrics show {total_clients} connected clients (max: {current_maxclients}), {blocked_clients} blocked clients, and {rejected_attempts} recent connection rejections. Please analyze the connection issues and provide immediate remediation steps."
            )

        finally:
            # Cleanup test connections
            self.print_step(4, "Cleaning up test connections and restoring settings")
            for conn in test_connections:
                try:
                    conn.close()
                except Exception:
                    pass

            # Restore original maxclients setting
            self.redis_client.config_set("maxclients", str(original_maxclients))
            print(f"   Restored maxclients to original value: {original_maxclients}")

            time.sleep(1)
            final_clients_info = self.redis_client.info("clients")
            final_clients = final_clients_info.get("connected_clients", 0)
            print(f"   Final connection count: {final_clients}")

    async def performance_scenario(self):
        """Simulate performance issues and demonstrate analysis."""
        self.print_header("Performance Analysis Scenario", "⚡")

        self.print_step(1, "Setting up performance test data")

        # Create different data structures to test performance
        test_data = {
            "simple_keys": 1000,
            "hash_keys": 100,
            "list_keys": 50,
            "set_keys": 50,
            "sorted_set_keys": 50,
        }

        print("   Creating test data structures...")

        # Clean up any existing test data
        existing_keys = self.redis_client.keys("demo:perf:*")
        if existing_keys:
            self.redis_client.delete(*existing_keys)

        # Create simple string keys
        pipe = self.redis_client.pipeline()
        for i in range(test_data["simple_keys"]):
            pipe.set(f"demo:perf:string:{i}", f"value_{i}_{random.randint(1000, 9999)}")
        pipe.execute()
        print(f"   ✅ Created {test_data['simple_keys']} string keys")

        # Create hash keys
        for i in range(test_data["hash_keys"]):
            hash_data = {f"field_{j}": f"value_{j}_{random.randint(1000, 9999)}" for j in range(20)}
            self.redis_client.hset(f"demo:perf:hash:{i}", mapping=hash_data)
        print(f"   ✅ Created {test_data['hash_keys']} hash keys")

        # Create list keys
        for i in range(test_data["list_keys"]):
            key = f"demo:perf:list:{i}"
            for j in range(100):
                self.redis_client.lpush(key, f"item_{j}_{random.randint(1000, 9999)}")
        print(f"   ✅ Created {test_data['list_keys']} list keys")

        self.print_step(2, "Running performance analysis and creating slow operations")

        # Create intentionally slow Lua script to generate real slowlog entries
        slow_lua_script = """
        -- Intentionally slow Lua script for performance demo
        local start_time = redis.call('TIME')
        local iterations = tonumber(ARGV[1]) or 100000

        -- Simulate CPU-intensive work
        local result = 0
        for i = 1, iterations do
            for j = 1, 100 do
                result = result + (i * j) % 1000
            end
        end

        -- Also do some Redis operations to make it realistic
        for i = 1, 10 do
            redis.call('SET', 'temp:slow:' .. i, 'processing_' .. result .. '_' .. i)
            redis.call('GET', 'temp:slow:' .. i)
            redis.call('DEL', 'temp:slow:' .. i)
        end

        local end_time = redis.call('TIME')
        return {result, end_time[1] - start_time[1], end_time[2] - start_time[2]}
        """

        print("   Creating intentionally slow operations to populate slowlog...")

        # Execute slow Lua script multiple times to create slowlog entries
        slow_times = []
        for i in range(3):
            try:
                print(f"   Executing slow operation {i + 1}/3...")
                start_time = time.time()
                # Adjust iterations to create operations that take 100-500ms
                self.redis_client.eval(slow_lua_script, 0, str(50000 + i * 10000))
                duration = time.time() - start_time
                slow_times.append(duration * 1000)  # Convert to milliseconds
                print(f"   Slow operation {i + 1} completed in {duration * 1000:.1f}ms")
                time.sleep(0.5)  # Brief pause between slow operations
            except Exception as e:
                print(f"   Warning: Slow operation {i + 1} failed: {e}")

        # Add some additional slow KEYS operations for variety in slowlog
        print("   Adding slow KEYS operations...")
        keys_times = []
        for pattern in ["demo:perf:*", "*perf*", "demo:*"]:
            start_time = time.time()
            keys = self.redis_client.keys(pattern)
            duration = time.time() - start_time
            keys_times.append(duration * 1000)
            print(f"   KEYS {pattern} found {len(keys)} keys in {duration * 1000:.1f}ms")

        # Test normal operations for comparison
        print("   Testing normal operation performance for comparison...")

        # Test string operations
        start_time = time.time()
        for i in range(100):
            self.redis_client.get(f"demo:perf:string:{i}")
        string_time = time.time() - start_time
        print(
            f"   100 GET operations: {string_time:.3f} seconds ({string_time / 100 * 1000:.2f}ms avg)"
        )

        # Test hash operations
        start_time = time.time()
        for i in range(50):
            self.redis_client.hgetall(f"demo:perf:hash:{i}")
        hash_time = time.time() - start_time
        print(
            f"   50 HGETALL operations: {hash_time:.3f} seconds ({hash_time / 50 * 1000:.2f}ms avg)"
        )

        # Show performance comparison
        avg_slow_time = sum(slow_times) / len(slow_times) if slow_times else 0
        avg_keys_time = sum(keys_times) / len(keys_times) if keys_times else 0

        print("\n   📊 Performance Summary:")
        print(f"   🐌 Average slow Lua script: {avg_slow_time:.1f}ms")
        print(f"   🐌 Average KEYS operation: {avg_keys_time:.1f}ms")
        print(f"   ✅ Average GET operation: {string_time / 100 * 1000:.2f}ms")
        print(f"   ✅ Average HGETALL operation: {hash_time / 50 * 1000:.2f}ms")

        if avg_slow_time > 50:
            print("   🚨 SLOW OPERATIONS DETECTED - These should appear in Redis slowlog!")

        # Check slowlog to verify our slow operations were recorded
        try:
            slowlog_entries = self.redis_client.slowlog_get(10)
            print(f"   📋 Current slowlog contains {len(slowlog_entries)} entries")

            if slowlog_entries:
                latest_entry = slowlog_entries[0]
                duration_us = latest_entry.get("duration", 0)
                command = " ".join(latest_entry.get("command", []))[:50] + "..."
                print(f"   🐌 Latest slow command: {command} ({duration_us}μs)")
        except Exception as e:
            print(f"   Warning: Could not check slowlog: {e}")

        # Run diagnostics and agent consultation with comprehensive performance data
        slowlog_count = 0
        try:
            slowlog_entries = self.redis_client.slowlog_get(10)
            slowlog_count = len(slowlog_entries)
        except Exception:
            pass

        await self._run_diagnostics_and_agent_query(
            f"Application performance issues reported. Performance analysis shows: slow Lua operations averaging {avg_slow_time:.1f}ms, KEYS operations averaging {avg_keys_time:.1f}ms, normal GET operations {string_time / 100 * 1000:.2f}ms, HGETALL operations {hash_time / 50 * 1000:.2f}ms. Slowlog contains {slowlog_count} entries. Please analyze the performance issues and provide optimization recommendations."
        )

        # Cleanup
        self.print_step(4, "Cleaning up performance test data")
        perf_keys = self.redis_client.keys("demo:perf:*")
        if perf_keys:
            # Use UNLINK for better performance on large datasets
            self.redis_client.delete(*perf_keys)
            print(f"   Cleaned up {len(perf_keys)} test keys")

    async def full_health_check(self):
        """Run comprehensive health check and agent consultation."""
        self.print_header("Full Health Check Scenario", "🏥")

        self.print_step(1, "Running comprehensive Redis diagnostics")

        # Run the full diagnostic suite
        health_checker = get_redis_diagnostics(self.redis_url)
        diagnostics = await health_checker.run_diagnostic_suite()

        # Display key results
        diagnostic_data = diagnostics.get("diagnostics", {})

        print("   📊 Diagnostic Results Summary:")

        # Memory diagnostics
        memory_diag = diagnostic_data.get("memory", {})
        if memory_diag:
            print(
                f"   💾 Memory: {memory_diag.get('used_memory_bytes', 0) / (1024 * 1024):.2f} MB used"
            )
            if (
                "memory_usage_percentage" in memory_diag
                and memory_diag["memory_usage_percentage"] is not None
            ):
                print(f"   💾 Memory utilization: {memory_diag['memory_usage_percentage']:.1f}%")
            if memory_diag.get("memory_fragmentation_ratio"):
                print(f"   💾 Fragmentation ratio: {memory_diag['memory_fragmentation_ratio']:.2f}")

        # Connection diagnostics
        connection_diag = diagnostic_data.get("connection", {})
        if connection_diag.get("basic_operations_test"):
            print(
                f"   🔗 Connectivity: OK (ping: {connection_diag.get('ping_duration_ms', 0):.1f}ms)"
            )
        else:
            print("   🔗 Connectivity: FAILED")

        # Keyspace diagnostics
        keyspace_diag = diagnostic_data.get("keyspace", {})
        total_keys = keyspace_diag.get("total_keys", 0)
        print(f"   🔑 Total keys: {total_keys}")

        # Performance diagnostics
        performance_diag = diagnostic_data.get("performance", {})
        hit_rate = performance_diag.get("hit_rate_percentage")
        if hit_rate is not None:
            print(f"   ⚡ Cache hit rate: {hit_rate:.1f}%")

        # Replication diagnostics
        replication_diag = diagnostic_data.get("replication", {})
        role = replication_diag.get("role", "unknown")
        print(f"   🔄 Role: {role}")

        # Persistence diagnostics
        persistence_diag = diagnostic_data.get("persistence", {})
        if persistence_diag.get("rdb_enabled"):
            print("   💿 RDB persistence: Enabled")
        if persistence_diag.get("aof_enabled"):
            print("   📝 AOF persistence: Enabled")

        # Security diagnostics
        security_diag = diagnostic_data.get("security", {})
        if security_diag.get("auth_required"):
            print("   🔒 Authentication: Required")
        else:
            print("   ⚠️  Authentication: Not configured")

        # Run comprehensive agent consultation
        await self._run_diagnostics_and_agent_query(
            f"Complete Redis health check completed. Total keys: {total_keys}, memory usage: {memory_diag.get('used_memory_bytes', 0) / (1024 * 1024):.1f}MB, role: {role}. Please provide a comprehensive health assessment and recommendations for optimization, security, and best practices."
        )

    async def _run_diagnostics_and_agent_query(self, query: str):
        """Run diagnostics and query the SRE agent."""
        self.print_step(4, "Consulting SRE Agent for expert analysis")

        try:
            print("   🤖 Analyzing situation with SRE expertise...")
            agent = get_sre_agent()

            response = await agent.process_query_with_fact_check(
                query=query.strip(), session_id="demo_scenario", user_id="sre_demo_user"
            )

            print("\n" + "=" * 60)
            print("🤖 SRE Agent Analysis & Recommendations")
            print("=" * 60)
            print(response)
            print("=" * 60)

        except Exception as e:
            print(f"   ⚠️  Agent query failed: {str(e)}")
            print("   This might be due to missing OpenAI API key or network issues.")

            # Provide fallback guidance based on scenario
            print("\n📋 Fallback Recommendations:")
            print("-" * 40)
            if "memory" in query.lower():
                print("1. Monitor memory usage with INFO memory")
                print("2. Set maxmemory and eviction policy if not configured")
                print("3. Use MEMORY USAGE to identify large keys")
                print("4. Consider data structure optimization")
            elif "connection" in query.lower():
                print("1. Monitor connection count with INFO clients")
                print("2. Review maxclients configuration")
                print("3. Implement connection pooling in applications")
                print("4. Set timeout for idle connections")
            elif "performance" in query.lower():
                print("1. Use SLOWLOG to identify slow commands")
                print("2. Avoid KEYS command in production")
                print("3. Optimize data structures and query patterns")
                print("4. Monitor command statistics with INFO commandstats")
            else:
                print("1. Regular health checks with INFO command")
                print("2. Monitor key metrics: memory, connections, performance")
                print("3. Implement proper security measures")
                print("4. Set up monitoring and alerting")

    def _format_diagnostics_for_agent(self, diagnostics: dict) -> str:
        """Format diagnostic data for inclusion in agent system prompt."""
        lines = ["## CURRENT REDIS DIAGNOSTIC DATA"]
        lines.append("(Automatically gathered - analyze this data to identify problems)")
        lines.append("")

        # Handle both formats: health_checker format and get_detailed_redis_diagnostics format
        if "diagnostics" in diagnostics:
            diagnostic_data = diagnostics.get("diagnostics", {})
        else:
            diagnostic_data = diagnostics

        # Memory diagnostics
        memory = diagnostic_data.get("memory", {})
        if memory and "error" not in memory:
            lines.append("### Memory Status")
            used_bytes = memory.get("used_memory_bytes", 0)
            max_bytes = memory.get("maxmemory_bytes", 0)

            def format_bytes(bytes_value: int) -> str:
                """Format bytes into human readable format."""
                if bytes_value == 0:
                    return "0 B"
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if bytes_value < 1024.0:
                        return f"{bytes_value:.1f} {unit}"
                    bytes_value /= 1024.0
                return f"{bytes_value:.1f} PB"

            if max_bytes > 0:
                utilization = (used_bytes / max_bytes) * 100
                lines.append(
                    f"- Used Memory: {format_bytes(used_bytes)} of {format_bytes(max_bytes)} ({utilization:.1f}%)"
                )
            else:
                lines.append(f"- Used Memory: {format_bytes(used_bytes)} (unlimited)")
            lines.append(f"- Max Memory: {format_bytes(max_bytes)}")
            lines.append(f"- Fragmentation Ratio: {memory.get('mem_fragmentation_ratio', 0):.2f}")
            lines.append(f"- Peak Memory: {format_bytes(memory.get('used_memory_peak_bytes', 0))}")
            lines.append("")

        # Configuration
        config = diagnostic_data.get("configuration", {})
        if config and "error" not in config:
            lines.append("### Critical Configuration")
            lines.append(f"- Maxmemory Policy: {config.get('maxmemory_policy', 'unknown')}")
            lines.append(f"- Save Configuration: {config.get('save', 'unknown')}")
            lines.append(f"- AOF Enabled: {config.get('appendonly', 'unknown')}")
            lines.append("")

        # Performance
        performance = diagnostic_data.get("performance", {})
        if performance and "error" not in performance:
            lines.append("### Performance Metrics")
            lines.append(f"- Ops/Second: {performance.get('instantaneous_ops_per_sec', 0)}")
            hits = performance.get("keyspace_hits", 0)
            misses = performance.get("keyspace_misses", 0)
            if hits + misses > 0:
                hit_rate = (hits / (hits + misses)) * 100
                lines.append(f"- Hit Rate: {hit_rate:.1f}%")
            lines.append(f"- Evicted Keys: {performance.get('evicted_keys', 0)}")
            lines.append("")

        # Clients
        clients = diagnostic_data.get("clients", {})
        if clients and "error" not in clients:
            lines.append("### Client Connections")
            lines.append(f"- Connected Clients: {clients.get('connected_clients', 0)}")
            lines.append(f"- Blocked Clients: {clients.get('blocked_clients', 0)}")
            lines.append("")

        # Keyspace
        keyspace = diagnostic_data.get("keyspace", {})
        if keyspace and "error" not in keyspace:
            lines.append("### Keyspace Data")
            lines.append(f"- Total Keys: {keyspace.get('total_keys', 0)}")
            databases = keyspace.get("databases", {})
            for db, info in databases.items():
                keys_count = info.get("keys", 0)
                expires_count = info.get("expires", 0)
                lines.append(f"- DB{db}: {keys_count} keys, {expires_count} with TTL")
                if keys_count > 0:
                    ttl_percentage = (expires_count / keys_count) * 100
                    lines.append(
                        f"  - TTL Coverage: {ttl_percentage:.1f}% (indicates cache vs persistent data)"
                    )
            lines.append("")

        # Sample keys (if available in diagnostic data)
        if "sample_keys" in diagnostic_data:
            lines.append("### Sample Keys (for pattern analysis)")
            sample_keys = diagnostic_data.get("sample_keys", [])
            for key in sample_keys[:10]:  # Show first 10 sample keys
                lines.append(f"- {key}")
            lines.append("")

        lines.append(
            "**INVESTIGATION REQUIRED**: Agent should analyze key patterns and persistence config to determine safe remediation steps"
        )

        return "\n".join(lines)

    async def _run_agent_with_diagnostics(self, query: str, diagnostic_data: str):
        """Run agent query with pre-loaded diagnostic data."""
        try:
            print("   🤖 Analyzing diagnostic data with SRE expertise...")
            agent = get_sre_agent()

            # Create enhanced query with diagnostic data
            enhanced_query = f"""DIAGNOSTIC DATA PROVIDED:

{diagnostic_data}

USER REQUEST: {query}

Analyze the diagnostic data above to identify problems and provide immediate remediation steps."""

            response = await agent.process_query_with_fact_check(
                query=enhanced_query, session_id="demo_scenario", user_id="sre_demo_user"
            )

            print("\n" + "=" * 60)
            print("🤖 SRE Agent Analysis & Recommendations")
            print("=" * 60)
            print(response)
            print("=" * 60)

        except Exception as e:
            print(f"   ⚠️  Agent query failed: {str(e)}")
            print("   This might be due to missing OpenAI API key or network issues.")

            # Provide fallback analysis based on diagnostic data
            print("\n📋 Fallback Analysis from Diagnostic Data:")
            print("-" * 40)
            if "maxmemory_policy" in diagnostic_data and "noeviction" in diagnostic_data:
                if "Memory Utilization: " in diagnostic_data:
                    print("⚠️  HIGH MEMORY USAGE WITH NOEVICTION POLICY DETECTED!")
                    print("1. Immediate: Change eviction policy to allkeys-lru")
                    print("2. Monitor: Set up memory usage alerts")
                    print("3. Investigate: Identify large keys consuming memory")

    async def run_interactive_demo(
        self, auto_run: bool = False, specific_scenario: Optional[str] = None
    ):
        """Run the interactive demo."""
        if not await self.setup_redis_connection():
            return

        if specific_scenario:
            if specific_scenario in self.scenarios:
                await self.scenarios[specific_scenario]()
            else:
                print(f"❌ Unknown scenario: {specific_scenario}")
                print(f"Available scenarios: {list(self.scenarios.keys())}")
            return

        if auto_run:
            # Run all scenarios automatically
            for name, scenario_func in self.scenarios.items():
                print(f"\n{'=' * 20} Running {name.title()} Scenario {'=' * 20}")
                await scenario_func()
                if name != list(self.scenarios.keys())[-1]:  # Don't wait after last scenario
                    print("\n⏸️  Pausing 3 seconds before next scenario...")
                    time.sleep(3)

            print("\n✅ All scenarios completed!")
            return

        # Interactive mode
        while True:
            choice = self.show_main_menu()

            if choice == "0":
                print("\n👋 Thank you for trying the Redis SRE Agent demo!")
                break
            elif choice == "1":
                await self.memory_pressure_scenario()
            elif choice == "2":
                await self.connection_issues_scenario()
            elif choice == "3":
                await self.performance_scenario()
            elif choice == "4":
                await self.full_health_check()
            elif choice == "5":
                print("\n🚀 Running all scenarios...")
                for name, scenario_func in self.scenarios.items():
                    print(f"\n{'=' * 15} {name.title()} Scenario {'=' * 15}")
                    await scenario_func()
                    if name != list(self.scenarios.keys())[-1]:
                        print("\n⏸️  Pausing 3 seconds before next scenario...")
                        time.sleep(3)
                print("\n✅ All scenarios completed!")

            # Ask if user wants to continue
            if choice in ["1", "2", "3", "4", "5"]:
                print("\n" + "-" * 60)
                try:
                    continue_choice = (
                        input("Continue with another scenario? (y/n): ").strip().lower()
                    )
                    if continue_choice not in ["y", "yes"]:
                        print("\n👋 Thank you for trying the Redis SRE Agent demo!")
                        break
                except KeyboardInterrupt:
                    print("\n👋 Demo interrupted by user")
                    break


async def main():
    """Main entry point for the demo."""
    parser = argparse.ArgumentParser(description="Redis SRE Agent Interactive Demo")
    parser.add_argument(
        "--scenario",
        choices=["memory", "connections", "performance", "health"],
        help="Run a specific scenario",
    )
    parser.add_argument(
        "--auto-run", action="store_true", help="Run all scenarios automatically without user input"
    )

    args = parser.parse_args()

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Agent queries may fail.")
        print("   Set this environment variable to enable full agent functionality.")
        print()

    # Run the demo
    demo = RedisSREDemo()
    await demo.run_interactive_demo(auto_run=args.auto_run, specific_scenario=args.scenario)


if __name__ == "__main__":
    asyncio.run(main())
