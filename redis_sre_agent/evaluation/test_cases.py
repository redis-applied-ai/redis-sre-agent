"""Test cases for Redis SRE Agent evaluation."""

from typing import Any, Dict, List

# Test case based on the memory demo scenario
REDIS_MEMORY_PRESSURE_TEST_CASE = {
    "id": "memory_pressure_scenario",
    "name": "Redis Memory Pressure Analysis",
    "description": "Agent should correctly analyze Redis memory pressure scenario and provide appropriate recommendations",
    "query": "I'm monitoring a Redis instance that just loaded 800 keys and is now using 7.6MB memory (76% utilization). As an expert SRE, please assess the current state, identify any concerns, and recommend appropriate actions based on the specific context and risk factors you observe.",
    "diagnostic_data": {
        "memory": {
            "used_memory_bytes": 7960576,
            "used_memory_human": "7.59M",
            "max_memory_bytes": 10485760,
            "max_memory_human": "10.00M",
            "memory_usage_percentage": 76.0,
            "memory_fragmentation_ratio": 4.32,
            "used_memory_peak": 7965184,
            "mem_allocator": "jemalloc-5.3.0",
        },
        "keyspace": {
            "total_keys": 800,
            "databases": {"db0": {"keys": 800, "expires": 0, "avg_ttl": 0}},
        },
        "performance": {
            "keyspace_hits": 7660000,
            "keyspace_misses": 18776,
            "hit_rate_percentage": 99.76,
            "instantaneous_ops_per_sec": 52,
            "evicted_keys": 0,
            "expired_keys": 87,
        },
        "configuration": {
            "maxmemory": "10485760",
            "maxmemory_policy": "noeviction",
            "save": "3600 1 300 100 60 10000",
            "appendonly": "no",
        },
        "connection": {"ping_duration_ms": 3.5, "basic_operations_test": True},
    },
    "expected_elements": [
        "Correct interpretation that Redis is entirely in-memory (no disk access for data retrieval)",
        "Accurate understanding that keyspace hit rate measures key existence, not memory vs disk performance",
        "Recognition that 76% memory utilization with 10MB limit is elevated and worth monitoring",
        "Analysis of memory fragmentation ratio (4.32 is concerning)",
        "Assessment of noeviction policy implications",
        "Recommendations for memory monitoring and potential optimizations",
        "Recognition that performance metrics (99.76% hit rate, 52 ops/sec) are healthy",
    ],
    "criteria": [
        {
            "name": "Technical Accuracy",
            "description": "Correct understanding of Redis concepts and metric interpretation",
            "weight": 1.0,
            "accuracy_points": [
                "Redis is entirely in-memory - no disk access for data retrieval",
                "Keyspace hit rate measures key existence (hits) vs non-existence (misses)",
                "Memory fragmentation ratio interpretation",
                "Understanding of eviction policies",
                "Correct Redis terminology usage",
            ],
            "required_elements": [
                "Correct keyspace hit rate explanation",
                "Accurate Redis memory model description",
            ],
        },
        {
            "name": "Diagnostic Analysis",
            "description": "Proper analysis of the provided diagnostic data",
            "weight": 1.0,
            "required_elements": [
                "76% memory utilization assessment",
                "Memory fragmentation ratio (4.32) analysis",
                "Keyspace data interpretation (800 keys)",
                "Performance metrics evaluation",
                "Configuration review (noeviction policy)",
            ],
        },
        {
            "name": "Risk Assessment",
            "description": "Appropriate risk analysis and prioritization",
            "weight": 1.0,
            "required_elements": [
                "Memory pressure evaluation",
                "Fragmentation concerns",
                "Eviction policy implications",
                "Growth trend considerations",
            ],
        },
        {
            "name": "Actionable Recommendations",
            "description": "Clear, specific, and appropriate recommendations",
            "weight": 1.0,
            "required_elements": [
                "Memory monitoring suggestions",
                "Fragmentation mitigation options",
                "Eviction policy considerations",
                "Preventive measures",
            ],
        },
    ],
}

# Test case for configuration analysis
REDIS_CONFIG_ANALYSIS_TEST_CASE = {
    "id": "redis_config_analysis",
    "name": "Redis Configuration Review",
    "description": "Agent should analyze Redis configuration and identify potential issues",
    "query": "Please review this Redis configuration and identify any potential issues or improvements for a production environment.",
    "diagnostic_data": {
        "configuration": {
            "maxmemory": "0",  # Unlimited memory - potential issue
            "maxmemory_policy": "noeviction",
            "save": "",  # No RDB persistence
            "appendonly": "no",  # No AOF persistence
            "timeout": "0",
            "tcp_keepalive": "300",
            "slowlog_log_slower_than": "10000",
            "maxclients": "10000",
            "protected_mode": "yes",
        },
        "memory": {
            "used_memory_bytes": 52428800,  # 50MB
            "max_memory_bytes": 0,  # Unlimited
            "memory_fragmentation_ratio": 1.2,
        },
        "persistence": {
            "rdb_changes_since_last_save": 1500,
            "rdb_last_save_time": 0,
            "aof_enabled": 0,
            "rdb_bgsave_in_progress": 0,
        },
    },
    "expected_elements": [
        "Identification of unlimited memory as a risk",
        "Recognition of no persistence configuration",
        "Analysis of eviction policy implications",
        "Production readiness assessment",
        "Specific configuration recommendations",
    ],
    "criteria": [
        {
            "name": "Configuration Expertise",
            "description": "Deep understanding of Redis configuration parameters",
            "weight": 1.0,
            "accuracy_points": [
                "maxmemory=0 means unlimited memory growth",
                "noeviction policy behavior when memory limit reached",
                "Persistence options (RDB vs AOF) implications",
                "Production vs development configuration differences",
            ],
        },
        {
            "name": "Risk Identification",
            "description": "Ability to identify configuration risks",
            "weight": 1.0,
            "required_elements": [
                "Unlimited memory risk assessment",
                "No persistence data loss implications",
                "Production environment concerns",
            ],
        },
        {
            "name": "Improvement Recommendations",
            "description": "Specific actionable configuration improvements",
            "weight": 1.0,
            "required_elements": [
                "Memory limit recommendations",
                "Persistence configuration suggestions",
                "Eviction policy options",
                "Monitoring and alerting setup",
            ],
        },
    ],
}

# Test case for performance troubleshooting
REDIS_PERFORMANCE_TEST_CASE = {
    "id": "redis_performance_issue",
    "name": "Redis Performance Troubleshooting",
    "description": "Agent should diagnose performance issues from slowlog and metrics",
    "query": "We're seeing increased response times in our Redis instance. Can you help diagnose what might be causing performance issues?",
    "diagnostic_data": {
        "slowlog": {
            "slowlog_length": 125,
            "slowlog_entries": [
                {
                    "id": 123,
                    "duration_ms": 15.5,
                    "command": "HGETALL large_hash",
                    "timestamp": 1692648000,
                    "client_name": "app_server_1",
                },
                {
                    "id": 122,
                    "duration_ms": 22.1,
                    "command": "KEYS user:*",  # Anti-pattern
                    "timestamp": 1692647950,
                    "client_name": "analytics_job",
                },
                {
                    "id": 121,
                    "duration_ms": 8.7,
                    "command": "ZRANGE leaderboard 0 -1",
                    "timestamp": 1692647900,
                    "client_name": "web_frontend",
                },
            ],
        },
        "performance": {
            "instantaneous_ops_per_sec": 3500,
            "keyspace_hits": 9500000,
            "keyspace_misses": 850000,
            "hit_rate_percentage": 91.8,
            "total_commands_processed": 15800000,
            "rejected_connections": 12,
        },
        "clients": {
            "connected_clients": 85,
            "blocked_clients": 8,
            "idle_connections_count": 25,
            "client_connections": [
                {"name": "analytics_job", "idle": 1800, "flags": "N"},
                {"name": "app_server_1", "idle": 0, "flags": "N"},
                {"name": "web_frontend", "idle": 5, "flags": "N"},
            ],
        },
        "memory": {
            "used_memory_bytes": 2147483648,  # 2GB
            "memory_fragmentation_ratio": 1.8,
            "mem_allocator": "jemalloc-5.3.0",
        },
    },
    "expected_elements": [
        "Analysis of slow queries and their impact",
        "Identification of KEYS command as anti-pattern",
        "Assessment of hit rate and connection patterns",
        "Memory fragmentation evaluation",
        "Specific optimization recommendations",
    ],
    "criteria": [
        {
            "name": "Performance Analysis",
            "description": "Ability to diagnose performance issues from metrics",
            "weight": 1.0,
            "accuracy_points": [
                "Slowlog analysis and interpretation",
                "Command pattern evaluation (KEYS is problematic)",
                "Hit rate implications (91.8% could be better)",
                "Connection and blocking client assessment",
            ],
        },
        {
            "name": "Root Cause Analysis",
            "description": "Identifying underlying causes of performance issues",
            "weight": 1.0,
            "required_elements": [
                "KEYS command impact identification",
                "Memory fragmentation effects",
                "Client connection patterns",
                "Query optimization opportunities",
            ],
        },
        {
            "name": "Optimization Recommendations",
            "description": "Specific recommendations to improve performance",
            "weight": 1.0,
            "required_elements": [
                "KEYS command alternatives (SCAN)",
                "Query optimization suggestions",
                "Connection management improvements",
                "Memory optimization strategies",
            ],
        },
    ],
}


def get_all_test_cases() -> List[Dict[str, Any]]:
    """Get all available test cases."""
    return [
        REDIS_MEMORY_PRESSURE_TEST_CASE,
        REDIS_CONFIG_ANALYSIS_TEST_CASE,
        REDIS_PERFORMANCE_TEST_CASE,
    ]


def get_memory_test_case() -> Dict[str, Any]:
    """Get the memory pressure test case."""
    return REDIS_MEMORY_PRESSURE_TEST_CASE


def get_config_test_case() -> Dict[str, Any]:
    """Get the configuration analysis test case."""
    return REDIS_CONFIG_ANALYSIS_TEST_CASE


def get_performance_test_case() -> Dict[str, Any]:
    """Get the performance troubleshooting test case."""
    return REDIS_PERFORMANCE_TEST_CASE
