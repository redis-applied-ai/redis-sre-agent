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

import asyncio
import argparse
import logging
import os
import random
import time
from typing import Dict, List, Optional

import redis

from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.tools.redis_diagnostics import RedisDiagnostics


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
            "health": self.full_health_check
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
            "redis_sre_agent.tools.prometheus_client"
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
        print("   For low memory demo: docker-compose -f docker-compose.yml -f docker-compose.test.yml up redis -d")
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
                if choice in ['0', '1', '2', '3', '4', '5']:
                    return choice
                else:
                    print("❌ Invalid choice, please select 0-5")
            except KeyboardInterrupt:
                print("\n👋 Demo interrupted by user")
                return '0'
    
    async def memory_pressure_scenario(self):
        """Run memory pressure analysis scenario."""
        self.print_header("Memory Pressure Analysis Scenario", "🧠")
        
        # Get baseline memory info
        initial_info = self.redis_client.info("memory")
        initial_memory = initial_info.get("used_memory", 0)
        maxmemory = initial_info.get("maxmemory", 0)
        
        self.print_step(1, "Checking initial Redis memory state")
        print(f"   Initial memory usage: {initial_memory / (1024*1024):.2f} MB")
        if maxmemory > 0:
            print(f"   Memory limit (maxmemory): {maxmemory / (1024*1024):.2f} MB")
            print(f"   Memory utilization: {(initial_memory / maxmemory * 100):.1f}%")
        else:
            print("   No memory limit set (maxmemory: 0)")
        
        self.print_step(2, "Loading Redis with data to simulate memory pressure")
        
        # Clear any existing demo keys first
        existing_keys = self.redis_client.keys("demo:memory:*")
        if existing_keys:
            self.redis_client.delete(*existing_keys)
            print(f"   Cleared {len(existing_keys)} existing demo keys")
        
        # Load data in batches
        batch_size = 100
        total_keys = 800  # Adjust based on memory limit
        key_size = 8192  # 8KB per key
        
        print(f"   Loading {total_keys} keys of {key_size} bytes each...")
        
        for batch in range(0, total_keys, batch_size):
            pipe = self.redis_client.pipeline()
            for i in range(batch, min(batch + batch_size, total_keys)):
                key = f"demo:memory:key:{i:04d}"
                value = f"data:{i}:{'x' * (key_size - 20)}"
                pipe.set(key, value)
            
            pipe.execute()
            progress = min(batch + batch_size, total_keys)
            print(f"   Progress: {progress}/{total_keys} keys loaded")
            
            if batch % 200 == 0:
                time.sleep(0.1)
        
        time.sleep(2)  # Wait for Redis to update memory stats
        
        self.print_step(3, "Analyzing memory state after data loading")
        after_info = self.redis_client.info("memory")
        after_memory = after_info.get("used_memory", 0)
        
        print(f"   Memory usage after loading: {after_memory / (1024*1024):.2f} MB")
        print(f"   Memory increase: {(after_memory - initial_memory) / (1024*1024):.2f} MB")
        
        utilization = 0
        if maxmemory > 0:
            utilization = after_memory / maxmemory * 100
            print(f"   Memory utilization: {utilization:.1f}%")
            
            if utilization > 80:
                print("   🚨 HIGH MEMORY USAGE DETECTED!")
            elif utilization > 60:
                print("   ⚠️  ELEVATED MEMORY USAGE")
        
        # Run diagnostics and agent consultation
        await self._run_diagnostics_and_agent_query(
            f"Redis memory analysis after loading {total_keys} keys - current usage {after_memory / (1024*1024):.1f}MB ({utilization:.1f}% utilization). Please assess the situation and provide memory optimization recommendations."
        )
        
        # Cleanup
        self.print_step(5, "Cleaning up demo data")
        demo_keys = self.redis_client.keys("demo:memory:*")
        if demo_keys:
            self.redis_client.delete(*demo_keys)
            print(f"   Cleaned up {len(demo_keys)} demo keys")
        
        final_info = self.redis_client.info("memory")
        final_memory = final_info.get("used_memory", 0)
        print(f"   Final memory usage: {final_memory / (1024*1024):.2f} MB")
    
    async def connection_issues_scenario(self):
        """Simulate connection issues and demonstrate troubleshooting."""
        self.print_header("Connection Issues Analysis Scenario", "🔗")
        
        self.print_step(1, "Analyzing current connection state")
        
        # Get connection info
        clients_info = self.redis_client.info("clients")
        current_clients = clients_info.get("connected_clients", 0)
        
        # Get maxclients setting
        try:
            maxclients_result = self.redis_client.config_get("maxclients")
            maxclients = int(maxclients_result.get("maxclients", 10000))
        except:
            maxclients = 10000
        
        print(f"   Current connected clients: {current_clients}")
        print(f"   Maximum clients allowed: {maxclients}")
        print(f"   Connection utilization: {(current_clients / maxclients * 100):.1f}%")
        
        self.print_step(2, "Simulating multiple client connections")
        
        # Create multiple connections to simulate load
        test_connections = []
        max_test_connections = min(50, maxclients // 4)  # Don't exceed 25% of limit
        
        print(f"   Creating {max_test_connections} test connections...")
        
        try:
            for i in range(max_test_connections):
                conn = redis.Redis(host="localhost", port=self.redis_port, decode_responses=True)
                conn.ping()  # Ensure connection is established
                test_connections.append(conn)
                
                if i % 10 == 0:
                    print(f"   Created {i + 1}/{max_test_connections} connections")
            
            # Check connection state after simulation
            time.sleep(1)
            clients_info_after = self.redis_client.info("clients")
            clients_after = clients_info_after.get("connected_clients", 0)
            
            print(f"   Connections after simulation: {clients_after}")
            print(f"   Connection increase: +{clients_after - current_clients}")
            
            if clients_after / maxclients > 0.8:
                print("   🚨 HIGH CONNECTION USAGE DETECTED!")
            elif clients_after / maxclients > 0.6:
                print("   ⚠️  ELEVATED CONNECTION USAGE")
            
            # Run diagnostics and agent consultation
            await self._run_diagnostics_and_agent_query(
                f"Redis connection analysis - currently {clients_after} connections out of {maxclients} maximum ({(clients_after / maxclients * 100):.1f}% utilization). Need guidance on connection management and troubleshooting potential connection issues."
            )
            
        finally:
            # Cleanup test connections
            self.print_step(4, "Cleaning up test connections")
            for conn in test_connections:
                try:
                    conn.close()
                except:
                    pass
            
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
            "sorted_set_keys": 50
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
        print(f"   100 GET operations: {string_time:.3f} seconds ({string_time/100*1000:.2f}ms avg)")
        
        # Test hash operations
        start_time = time.time()
        for i in range(50):
            self.redis_client.hgetall(f"demo:perf:hash:{i}")
        hash_time = time.time() - start_time
        print(f"   50 HGETALL operations: {hash_time:.3f} seconds ({hash_time/50*1000:.2f}ms avg)")
        
        if hash_time / 50 > 0.01:  # > 10ms per operation
            print("   ⚠️  SLOW HASH operations detected!")
        
        # Run diagnostics and agent consultation
        await self._run_diagnostics_and_agent_query(
            f"Redis performance analysis completed. KEYS scan took {scan_time:.3f}s for {len(all_keys)} keys, average GET latency {string_time/100*1000:.2f}ms, average HGETALL latency {hash_time/50*1000:.2f}ms. Please analyze performance and suggest optimizations."
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
            print(f"   💾 Memory: {memory_diag.get('used_memory_bytes', 0) / (1024*1024):.2f} MB used")
            if "memory_usage_percentage" in memory_diag and memory_diag["memory_usage_percentage"] is not None:
                print(f"   💾 Memory utilization: {memory_diag['memory_usage_percentage']:.1f}%")
            if memory_diag.get("memory_fragmentation_ratio"):
                print(f"   💾 Fragmentation ratio: {memory_diag['memory_fragmentation_ratio']:.2f}")
        
        # Connection diagnostics
        connection_diag = diagnostic_data.get("connection", {})
        if connection_diag.get("basic_operations_test"):
            print(f"   🔗 Connectivity: OK (ping: {connection_diag.get('ping_duration_ms', 0):.1f}ms)")
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
            f"Complete Redis health check completed. Total keys: {total_keys}, memory usage: {memory_diag.get('used_memory_bytes', 0) / (1024*1024):.1f}MB, role: {role}. Please provide a comprehensive health assessment and recommendations for optimization, security, and best practices."
        )
    
    async def _run_diagnostics_and_agent_query(self, query: str):
        """Run diagnostics and query the SRE agent."""
        self.print_step(4, "Consulting SRE Agent for expert analysis")
        
        try:
            print("   🤖 Analyzing situation with SRE expertise...")
            agent = get_sre_agent()
            
            response = await agent.process_query_with_fact_check(
                query=query.strip(),
                session_id="demo_scenario",
                user_id="sre_demo_user"
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
            print(f"\n📋 Fallback Recommendations:")
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
    
    async def run_interactive_demo(self, auto_run: bool = False, specific_scenario: Optional[str] = None):
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
                print(f"\n{'='*20} Running {name.title()} Scenario {'='*20}")
                await scenario_func()
                if name != list(self.scenarios.keys())[-1]:  # Don't wait after last scenario
                    print("\n⏸️  Pausing 3 seconds before next scenario...")
                    time.sleep(3)
            
            print("\n✅ All scenarios completed!")
            return
        
        # Interactive mode
        while True:
            choice = self.show_main_menu()
            
            if choice == '0':
                print("\n👋 Thank you for trying the Redis SRE Agent demo!")
                break
            elif choice == '1':
                await self.memory_pressure_scenario()
            elif choice == '2':
                await self.connection_issues_scenario()
            elif choice == '3':
                await self.performance_scenario()
            elif choice == '4':
                await self.full_health_check()
            elif choice == '5':
                print("\n🚀 Running all scenarios...")
                for name, scenario_func in self.scenarios.items():
                    print(f"\n{'='*15} {name.title()} Scenario {'='*15}")
                    await scenario_func()
                    if name != list(self.scenarios.keys())[-1]:
                        print("\n⏸️  Pausing 3 seconds before next scenario...")
                        time.sleep(3)
                print("\n✅ All scenarios completed!")
            
            # Ask if user wants to continue
            if choice in ['1', '2', '3', '4', '5']:
                print("\n" + "-" * 60)
                try:
                    continue_choice = input("Continue with another scenario? (y/n): ").strip().lower()
                    if continue_choice not in ['y', 'yes']:
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
        help="Run a specific scenario"
    )
    parser.add_argument(
        "--auto-run", 
        action="store_true",
        help="Run all scenarios automatically without user input"
    )
    
    args = parser.parse_args()
    
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Agent queries may fail.")
        print("   Set this environment variable to enable full agent functionality.")
        print()
    
    # Run the demo
    demo = RedisSREDemo()
    await demo.run_interactive_demo(
        auto_run=args.auto_run,
        specific_scenario=args.scenario
    )



if __name__ == "__main__":
    asyncio.run(main())
