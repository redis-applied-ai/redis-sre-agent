# Redis SRE Agent - Interactive Demo

This is a comprehensive demonstration of the Redis SRE Agent's capabilities through realistic scenarios that simulate real-world Redis issues and showcase the agent's diagnostic and troubleshooting abilities.

## 🎯 Demo Philosophy

The Redis SRE Agent demo takes a **hands-on approach** by:
- **Creating realistic problems** in a Redis instance
- **Demonstrating real-time diagnostics** with actual metrics
- **Showing expert-level analysis** and remediation steps
- **Providing interactive scenarios** that you can run and observe

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Demo Scenarios │    │      Redis      │    │    SRE Agent    │
│   (Problems)    │───►│   (Instance)    │◄──►│   (Analysis)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         │                        ▼                        ▼
         │              ┌─────────────────┐    ┌─────────────────┐
         └─────────────►│   Diagnostics   │    │  Recommendations│
                        │   (Real Data)   │    │ (Expert Advice) │
                        └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Ensure you have Redis running locally
redis-server --port 6379

# Or use Docker
docker run -d -p 6379:6379 redis:latest

# Install dependencies
uv sync --dev
```

### 2. Set Environment Variables

```bash
# Required: OpenAI API key for the agent
export OPENAI_API_KEY="your_openai_key_here"

# Optional: Redis connection (defaults to localhost:6379)
export REDIS_URL="redis://localhost:6379/0"
```

### 3. Run Interactive Demo Scenarios

```bash
# Health check scenario - comprehensive Redis analysis
uv run python examples/demo_scenarios.py --scenario health

# Memory pressure scenario - simulate and resolve memory issues
uv run python examples/demo_scenarios.py --scenario memory

# Performance scenario - identify and fix slow operations
uv run python examples/demo_scenarios.py --scenario performance

# Connection issues scenario - diagnose client connection problems
uv run python examples/demo_scenarios.py --scenario connections
```

### 4. What You'll See

Each scenario will:
1. **Set up the problem** - Modify Redis to create realistic issues
2. **Show real metrics** - Display actual Redis diagnostics and performance data
3. **Consult the SRE Agent** - Get expert analysis and recommendations
4. **Clean up** - Restore Redis to a clean state

**Example Output:**
```
✅ Redis connection established on port 7844 (database cleared for clean demo)

=============== 🏥 Health Check Scenario 🏥 ===============

📋 Step 1: Analyzing current Redis health status
--------------------------------------------------
   Current Redis metrics:
   📊 Memory: 1.2MB used (0.1% of system)
   🔗 Connections: 1 clients connected
   ⚡ Performance: 0 ops/sec, 100% hit rate
   💾 Persistence: RDB enabled, last save 2 minutes ago

📋 Step 2: Consulting SRE Agent for expert analysis
--------------------------------------------------
   🤖 Analyzing Redis health with SRE expertise...

============================================================
🤖 SRE Agent Analysis & Recommendations
============================================================
### Current Health Status: ✅ HEALTHY
- Memory usage is optimal at 0.1%
- No performance bottlenecks detected
- Persistence configuration is appropriate
- Security recommendations: Enable AUTH, disable dangerous commands
============================================================
```

## 🛠️ SRE Agent Capabilities Demonstrated

### 1. Real-Time Redis Diagnostics
- **Memory Analysis**: Usage patterns, fragmentation, eviction policies
- **Performance Metrics**: Operations per second, hit rates, latency analysis
- **Connection Monitoring**: Client connections, blocked clients, timeouts
- **Slow Query Detection**: Identifies and analyzes slow operations
- **Configuration Validation**: Security settings, persistence, limits

### 2. Problem Simulation & Resolution
- **Memory Pressure**: Creates high memory usage scenarios and provides optimization strategies
- **Performance Bottlenecks**: Simulates slow Lua scripts and KEYS operations, recommends SCAN alternatives
- **Connection Issues**: Demonstrates client limit problems and connection pooling solutions
- **Configuration Problems**: Shows misconfiguration impacts and provides specific CONFIG SET commands

### 3. Expert-Level Analysis
- **Evidence-Based Recommendations**: References specific metrics and thresholds
- **Operational Focus**: Provides immediate, actionable steps
- **Runbook Integration**: Cites relevant documentation and best practices
- **Multi-Turn Conversations**: Maintains context across follow-up questions

### 4. Extensible Architecture
- **Protocol-Based Tools**: Supports custom metrics, logs, tickets, repos, and traces providers
- **Backward Compatibility**: Works with existing hardcoded tools
- **Provider Registry**: Dynamic discovery and registration of tool providers

## 📋 Available Demo Scenarios

### 🏥 Health Check Scenario (`--scenario health`)
**Purpose**: Comprehensive Redis health analysis
**What it does**:
- Analyzes current Redis metrics (memory, connections, performance)
- Checks persistence configuration and security settings
- Provides baseline health assessment and recommendations

**Key Learning**: How the agent performs systematic health checks and identifies potential issues before they become problems.

### 💾 Memory Pressure Scenario (`--scenario memory`)
**Purpose**: Simulate and resolve memory-related issues
**What it does**:
- Creates memory pressure by adding large amounts of data
- Demonstrates memory fragmentation and eviction scenarios
- Shows how the agent identifies memory issues and provides optimization strategies

**Key Learning**: Memory management best practices, eviction policies, and when to scale Redis.

### ⚡ Performance Scenario (`--scenario performance`)
**Purpose**: Identify and fix performance bottlenecks
**What it does**:
- Creates slow Lua scripts and inefficient KEYS operations
- Populates Redis slowlog with problematic queries
- Demonstrates how the agent analyzes performance metrics and recommends optimizations

**Key Learning**: Performance tuning, slow query analysis, and replacing O(N) operations with efficient alternatives.

### 🔗 Connection Issues Scenario (`--scenario connections`)
**Purpose**: Diagnose client connection problems
**What it does**:
- Simulates connection limit issues and client timeouts
- Creates scenarios with blocked clients and connection pooling problems
- Shows how the agent identifies connection bottlenecks

**Key Learning**: Connection management, client limits, and connection pooling strategies.



## 🎯 Example Demo Output

### Memory Pressure Scenario Results

```
=============== 💾 Memory Pressure Scenario 💾 ===============

📋 Step 1: Creating memory pressure conditions
--------------------------------------------------
   Adding large datasets to simulate memory pressure...
   ✅ Created 10000 string keys (avg 1KB each)
   ✅ Created 1000 hash objects (avg 5KB each)
   ✅ Created 500 list objects (avg 10KB each)
   📊 Total memory used: ~20MB

📋 Step 2: Analyzing memory usage and fragmentation
--------------------------------------------------
   Current memory metrics:
   💾 Used memory: 20.5MB (80% of configured limit)
   📈 Memory fragmentation ratio: 1.45
   🔄 Evicted keys: 0 (no evictions yet)
   ⚠️  Memory pressure detected - approaching maxmemory limit

📋 Step 3: Consulting SRE Agent for expert analysis
--------------------------------------------------
   🤖 Analyzing memory pressure with SRE expertise...

============================================================
🤖 SRE Agent Analysis & Recommendations
============================================================
### Problem Assessment
- **Current Memory Usage**: 80% of maxmemory limit (20.5MB/25MB)
- **Fragmentation**: 1.45 ratio indicates memory fragmentation
- **Risk Level**: HIGH - Approaching eviction threshold

### Immediate Actions Required
1. **Increase maxmemory limit**:
   CONFIG SET maxmemory 50mb

2. **Enable memory defragmentation**:
   CONFIG SET activedefrag yes
   MEMORY PURGE

3. **Configure eviction policy**:
   CONFIG SET maxmemory-policy allkeys-lru

4. **Monitor key patterns**:
   - Review large keys with MEMORY USAGE command
   - Consider data structure optimization
   - Implement TTL policies for temporary data

### Long-term Recommendations
- Set up memory usage alerts at 70% threshold
- Implement data archiving for old keys
- Consider Redis clustering for horizontal scaling
============================================================
```

### Performance Scenario Results

```
=============== ⚡ Performance Analysis Scenario ⚡ ===============

📋 Step 2: Running performance analysis and creating slow operations
--------------------------------------------------
   Creating intentionally slow operations to populate slowlog...
   Slow operation 1 completed in 34.8ms
   Slow operation 2 completed in 49.2ms
   Slow operation 3 completed in 68.1ms

   📊 Performance Summary:
   🐌 Average slow Lua script: 50.7ms
   🐌 Average KEYS operation: 3.5ms
   ✅ Average GET operation: 0.27ms
   🚨 SLOW OPERATIONS DETECTED - These should appear in Redis slowlog!

============================================================
🤖 SRE Agent Analysis & Recommendations
============================================================
### Problem Assessment
- **Lua Scripts**: Averaging 50.7ms (blocking Redis single thread)
- **KEYS Commands**: 3.5ms each (O(N) scan of entire keyspace)
- **Impact**: Risk of client blocking and latency spikes under load

### Immediate Actions Required
1. **Refactor Lua Scripts**: Break up long loops, set lua-time-limit
2. **Replace KEYS with SCAN**: Use incremental iteration
3. **Pipeline Operations**: Bundle multiple commands to reduce RTT
4. **Monitor Slowlog**: Set up alerts for slow operations

### Solution Sources
- Runbook: Redis Lua Script Timeout Blocking Server (Part 3)
- Runbook: Redis Performance Latency Investigation (Part 2)
============================================================
```

## 🔧 Configuration & Customization

### Environment Variables

```bash
# Required
OPENAI_API_KEY=your_openai_key_here

# Optional Redis connection (defaults to localhost:6379)
REDIS_URL=redis://localhost:6379/0

# Optional: Custom Redis port for demos (auto-selected if not set)
DEMO_REDIS_PORT=6380
```

### Demo Customization

You can customize the demo scenarios by modifying `examples/demo_scenarios.py`:

```python
# Adjust memory pressure amounts
MEMORY_PRESSURE_CONFIG = {
    "string_keys": 10000,    # Number of string keys to create
    "hash_objects": 1000,    # Number of hash objects
    "list_objects": 500,     # Number of list objects
    "key_size_kb": 1,        # Average size per key in KB
}

# Customize performance test parameters
PERFORMANCE_CONFIG = {
    "slow_script_count": 3,      # Number of slow Lua scripts to run
    "keys_operations": 3,        # Number of KEYS commands to execute
    "normal_ops_count": 100,     # Number of normal operations for comparison
}
```

### Protocol-Based Tool Configuration

For advanced users, you can configure custom tool providers:

```python
from redis_sre_agent.tools.registry import get_global_registry
from redis_sre_agent.tools.providers import create_redis_provider

# Register custom Redis provider
registry = get_global_registry()
custom_provider = create_redis_provider(
    redis_url="redis://custom-host:6379",
    prometheus_url="http://prometheus:9090"  # Optional
)
registry.register_provider("custom-redis", custom_provider)
```

## 📈 Understanding the Agent's Analysis

### What Makes the Agent Effective

1. **Real Data Analysis**: The agent analyzes actual Redis metrics, not simulated data
2. **Contextual Recommendations**: Suggestions are tailored to the specific problem scenario
3. **Operational Focus**: Provides immediate, actionable steps with exact commands
4. **Evidence-Based**: References specific metrics, thresholds, and diagnostic evidence
5. **Runbook Integration**: Cites relevant documentation and best practices

### Key Metrics the Agent Analyzes

- **Memory Metrics**: `used_memory`, `used_memory_rss`, `mem_fragmentation_ratio`, `maxmemory`
- **Performance Metrics**: `instantaneous_ops_per_sec`, `keyspace_hits`, `keyspace_misses`
- **Connection Metrics**: `connected_clients`, `blocked_clients`, `rejected_connections`
- **Persistence Metrics**: `rdb_last_save_time`, `aof_enabled`, `rdb_changes_since_last_save`
- **Slowlog Analysis**: Identifies slow operations and provides optimization recommendations

## 🧪 Testing & Development

### Running the Test Suite

```bash
# Run all tests (258 tests, 100% pass rate)
uv run pytest

# Run with coverage report
uv run pytest --cov=redis_sre_agent --cov-report=html

# Test specific components
uv run pytest tests/unit/test_protocol_tools.py -v  # Protocol-based tools
uv run pytest tests/unit/test_providers.py -v      # Provider implementations
```

### Manual Testing of Components

```bash
# Test Redis diagnostics directly
uv run python -c "
from redis_sre_agent.tools.redis_diagnostics import get_redis_diagnostics
import asyncio
async def test():
    diag = get_redis_diagnostics()
    result = await diag.run_diagnostic_suite()
    print(result)
asyncio.run(test())
"

# Test Protocol-based tools
uv run python examples/custom_provider_setup.py
```

### Creating Custom Scenarios

You can create your own demo scenarios by following the pattern in `examples/demo_scenarios.py`:

```python
async def custom_scenario():
    """Create your own Redis problem scenario."""
    # 1. Set up the problem
    await redis_client.set("problem_key", "large_value" * 1000)

    # 2. Gather diagnostics
    diagnostics = await get_redis_diagnostics()

    # 3. Consult the agent
    agent = get_sre_agent()
    response = await agent.ainvoke({
        "messages": [{"role": "user", "content": "Analyze this Redis issue..."}]
    })

    # 4. Display results and clean up
    print(response)
    await redis_client.delete("problem_key")
```

## 🚨 Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   ```bash
   # Check if Redis is running
   redis-cli ping

   # Start Redis if needed
   redis-server --port 6379

   # Or use Docker
   docker run -d -p 6379:6379 redis:latest
   ```

2. **OpenAI API Issues**
   ```bash
   # Verify API key is set
   echo $OPENAI_API_KEY

   # Test API connectivity
   uv run python -c "
   import openai
   client = openai.OpenAI()
   print('API key is valid:', bool(client.models.list().data))
   "
   ```

3. **Demo Scenarios Not Working**
   ```bash
   # Check Redis connection in demo
   uv run python -c "
   import redis
   r = redis.Redis(host='localhost', port=6379)
   print('Redis ping:', r.ping())
   "

   # Run with debug output
   export LOG_LEVEL=DEBUG
   uv run python examples/demo_scenarios.py --scenario health
   ```

4. **Port Conflicts**
   ```bash
   # Demo automatically finds available ports, but you can specify:
   export DEMO_REDIS_PORT=6380
   uv run python examples/demo_scenarios.py --scenario health
   ```

## 🚀 Next Steps

### For Learning & Exploration
1. **Run all scenarios** to see different types of Redis issues and solutions
2. **Modify scenarios** to create your own problem situations
3. **Explore the agent's responses** to understand SRE best practices
4. **Try follow-up questions** to see how the agent maintains context

### For Development & Integration
1. **Explore Protocol-based tools** in `redis_sre_agent/tools/protocols.py`
2. **Create custom providers** for your monitoring systems
3. **Integrate with your infrastructure** using the provider registry
4. **Extend scenarios** for your specific Redis use cases

### For Production Use
1. **Set up monitoring integration** with Prometheus, Grafana, or your monitoring stack
2. **Configure custom providers** for your logs, tickets, and repository systems
3. **Deploy the agent API** for team-wide access
4. **Create custom runbooks** and integrate them with the knowledge base

## 🎉 What This Demo Demonstrates

This interactive demo showcases a complete SRE agent system with:

✅ **Real Problem Simulation**: Creates actual Redis issues, not mock scenarios
✅ **Expert-Level Analysis**: Provides detailed diagnostics with specific metrics
✅ **Actionable Recommendations**: Gives exact commands and configuration changes
✅ **Evidence-Based Reasoning**: References specific data points and thresholds
✅ **Operational Focus**: Emphasizes immediate actions and long-term strategies
✅ **Extensible Architecture**: Supports custom tools and integrations via Protocols
✅ **Production Ready**: Built with real-world SRE practices and patterns
✅ **Comprehensive Testing**: 258 tests with 100% pass rate and 45% coverage

### Why This Approach Works

The demo's **hands-on methodology** effectively demonstrates the agent's capabilities because:

- **Real Data**: Uses actual Redis metrics and diagnostics, not simulated data
- **Realistic Problems**: Creates genuine issues that SREs encounter in production
- **Interactive Learning**: Shows the problem, analysis, and solution in sequence
- **Immediate Feedback**: You can see the agent's reasoning and recommendations instantly
- **Safe Environment**: Problems are contained and automatically cleaned up

The Redis SRE Agent transforms complex operational knowledge into accessible, actionable guidance - making every engineer more effective at Redis operations! 🎯
