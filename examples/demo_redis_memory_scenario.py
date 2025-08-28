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
from typing import Optional

import redis

from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.tools.redis_diagnostics import RedisDiagnostics
from redis_sre_agent.tools.sre_functions import get_detailed_redis_diagnostics


class RedisSREDemo:
    """Interactive Redis SRE Agent demonstration."""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.redis_port: Optional[int] = None
        self.health_checker: Optional[RedisDiagnostics] = None
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
        redis_ports = [7942, 6379]  # Try low-memory test port first, then default

        for port in redis_ports:
            try:
                self.redis_client = redis.Redis(host="localhost", port=port, decode_responses=True)
                self.redis_client.ping()
                self.redis_port = port
                self.health_checker = RedisDiagnostics(f"redis://localhost:{port}/0")
                print(f"✅ Redis connection established on port {port}")
                return True
            except redis.ConnectionError:
                continue

        print("❌ Redis not available on any port. Please start Redis first:")
        print(
            "   For low memory demo: docker-compose -f docker-compose.yml -f docker-compose.test.yml up redis -d"
        )
        print("   For regular demo: docker-compose up redis -d")
        return False

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
        diagnostics = await get_detailed_redis_diagnostics()

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

        self.print_step(1, "Analyzing current connection state")

        # Get connection info
        clients_info = self.redis_client.info("clients")
        current_clients = clients_info.get("connected_clients", 0)

        # Get original maxclients setting
        try:
            maxclients_result = self.redis_client.config_get("maxclients")
            original_maxclients = int(maxclients_result.get("maxclients", 10000))
        except Exception:
            original_maxclients = 10000

        print(f"   Current connected clients: {current_clients}")
        print(f"   Original maximum clients: {original_maxclients}")

        self.print_step(2, "Creating connection pressure scenario")

        # Set a low connection limit to create a realistic demo scenario
        # This simulates a constrained environment or misconfiguration
        demo_maxclients = 75  # Low limit to create pressure with our test connections
        
        print(f"   Setting maxclients to {demo_maxclients} for connection pressure demo...")
        self.redis_client.config_set("maxclients", str(demo_maxclients))
        
        # Verify the setting was applied
        updated_result = self.redis_client.config_get("maxclients")
        current_maxclients = int(updated_result.get("maxclients", demo_maxclients))
        print(f"   Connection limit reduced to: {current_maxclients}")
        print(f"   Current utilization: {(current_clients / current_maxclients * 100):.1f}%")

        self.print_step(3, "Simulating connection flood attack")

        # Create connections that will approach the limit
        test_connections = []
        # Target 85-90% of the connection limit
        target_connections = int(current_maxclients * 0.85) - current_clients
        target_connections = max(20, min(target_connections, 60))  # Ensure reasonable range

        print(f"   Attempting to create {target_connections} concurrent connections...")
        print(f"   This will push utilization to ~85% of the {current_maxclients} connection limit")

        connection_errors = 0
        successful_connections = 0
        
        try:
            for i in range(target_connections):
                try:
                    conn = redis.Redis(
                        host="localhost", 
                        port=self.redis_port, 
                        decode_responses=True,
                        socket_connect_timeout=2,  # Short timeout to detect connection issues
                        socket_timeout=2
                    )
                    conn.ping()  # Ensure connection is established
                    test_connections.append(conn)
                    successful_connections += 1

                    if (i + 1) % 15 == 0 or i == target_connections - 1:
                        print(f"   Progress: {i + 1}/{target_connections} connections attempted...")
                    
                    # Add some delay to simulate realistic connection patterns
                    time.sleep(0.05)
                    
                except redis.ConnectionError as e:
                    connection_errors += 1
                    if connection_errors == 1:
                        print(f"   ⚠️  Connection rejected: {str(e)}")
                        print(f"   This indicates we're hitting Redis connection limits!")
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
            print(f"   📈 Connection utilization: {(clients_after / current_maxclients * 100):.1f}%")

            if clients_after / current_maxclients > 0.9:
                print("   🚨 CRITICAL: Connection exhaustion imminent!")
            elif clients_after / current_maxclients > 0.8:
                print("   🚨 HIGH CONNECTION USAGE DETECTED!")
            elif clients_after / current_maxclients > 0.6:
                print("   ⚠️  ELEVATED CONNECTION USAGE")

            # Add some blocked clients by trying to create more connections
            if connection_errors == 0:  # Only if we haven't hit limits yet
                print("   🧪 Testing connection limit by creating additional connections...")
                extra_attempts = 5
                blocked_attempts = 0
                for i in range(extra_attempts):
                    try:
                        extra_conn = redis.Redis(
                            host="localhost", 
                            port=self.redis_port, 
                            socket_connect_timeout=1
                        )
                        extra_conn.ping()
                        test_connections.append(extra_conn)
                    except:
                        blocked_attempts += 1
                
                if blocked_attempts > 0:
                    print(f"   🚨 {blocked_attempts}/{extra_attempts} additional connection attempts blocked!")

            # Run diagnostics and agent consultation
            await self._run_diagnostics_and_agent_query(
                "The application team has reported user complaints. Please analyze the Redis diagnostics and provide recommendations."
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

        self.print_step(2, "Running performance analysis")

        # Simulate some potentially slow operations
        print("   Testing key scanning performance...")
        start_time = time.time()
        all_keys = self.redis_client.keys("demo:perf:*")
        scan_time = time.time() - start_time
        print(f"   KEYS scan found {len(all_keys)} keys in {scan_time:.3f} seconds")

        if scan_time > 0.1:
            print("   ⚠️  SLOW KEYS operation detected!")

        # Test individual operations
        print("   Testing individual operation performance...")

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

        if hash_time / 50 > 0.01:  # > 10ms per operation
            print("   ⚠️  SLOW HASH operations detected!")

        # Run diagnostics and agent consultation
        await self._run_diagnostics_and_agent_query(
            f"Redis performance analysis completed. KEYS scan took {scan_time:.3f}s for {len(all_keys)} keys, average GET latency {string_time / 100 * 1000:.2f}ms, average HGETALL latency {hash_time / 50 * 1000:.2f}ms. Please analyze performance and suggest optimizations."
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
        diagnostics = await self.health_checker.run_diagnostic_suite()

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
            lines.append(
                f"- Used Memory: {memory.get('used_memory_bytes', 0):,} bytes ({memory.get('used_memory_bytes', 0) / (1024 * 1024):.2f} MB)"
            )
            lines.append(
                f"- Max Memory: {memory.get('maxmemory_bytes', 0):,} bytes ({memory.get('maxmemory_bytes', 0) / (1024 * 1024):.2f} MB)"
            )
            if memory.get("maxmemory_bytes", 0) > 0:
                utilization = (
                    memory.get("used_memory_bytes", 0) / memory.get("maxmemory_bytes", 1)
                ) * 100
                lines.append(f"- Memory Utilization: {utilization:.1f}%")
            else:
                lines.append("- Memory Utilization: Unlimited (no maxmemory set)")
            lines.append(f"- Fragmentation Ratio: {memory.get('mem_fragmentation_ratio', 0):.2f}")
            lines.append(f"- Peak Memory: {memory.get('used_memory_peak_bytes', 0):,} bytes")
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
