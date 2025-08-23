#!/usr/bin/env python3
"""
External Redis diagnostic capture script.

This script captures baseline Redis diagnostic data for agent analysis.
It provides the same interface as the agent tools, enabling realistic
production workflow testing where both external tools and agents use
the same diagnostic functions.

Usage:
    # Capture all diagnostics
    python scripts/capture_redis_diagnostics.py

    # Capture specific sections
    python scripts/capture_redis_diagnostics.py --sections memory performance

    # Save to file for agent input
    python scripts/capture_redis_diagnostics.py --output baseline.json

    # Display summary metrics
    python scripts/capture_redis_diagnostics.py --summary
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from redis_sre_agent.tools.redis_diagnostics import capture_redis_diagnostics


def format_bytes(bytes_value: int) -> str:
    """Format bytes into human readable format."""
    if bytes_value == 0:
        return "0 B"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def display_summary(diagnostic_data: dict):
    """Display a summary of key Redis metrics."""
    print("=" * 60)
    print("REDIS DIAGNOSTIC SUMMARY")
    print("=" * 60)
    print(f"Timestamp: {diagnostic_data.get('timestamp', 'Unknown')}")
    print(f"Redis URL: {diagnostic_data.get('redis_url', 'Unknown')}")
    print(f"Sections: {', '.join(diagnostic_data.get('sections_captured', []))}")
    print(f"Status: {diagnostic_data.get('capture_status', 'Unknown')}")
    print()

    diagnostics = diagnostic_data.get("diagnostics", {})

    # Connection status
    connection = diagnostics.get("connection", {})
    if connection:
        print("CONNECTION:")
        print(f"  Ping Response: {connection.get('ping_response', 'N/A')}")
        print(f"  Ping Time: {connection.get('ping_duration_ms', 'N/A')} ms")
        print(f"  Basic Ops Test: {'✓' if connection.get('basic_operations_test') else '✗'}")
        print()

    # Memory metrics
    memory = diagnostics.get("memory", {})
    if memory and "error" not in memory:
        print("MEMORY:")
        used_bytes = memory.get("used_memory_bytes", 0)
        max_bytes = memory.get("maxmemory_bytes", 0)
        print(
            f"  Used Memory: {format_bytes(used_bytes)} ({memory.get('used_memory_human', 'N/A')})"
        )

        if max_bytes > 0:
            usage_pct = (used_bytes / max_bytes) * 100
            print(
                f"  Max Memory: {format_bytes(max_bytes)} ({memory.get('maxmemory_human', 'N/A')})"
            )
            print(f"  Usage: {usage_pct:.1f}%")

            # Status indicators
            if usage_pct >= 95:
                print("  Status: 🔴 CRITICAL - Memory usage above 95%")
            elif usage_pct >= 85:
                print("  Status: 🟡 WARNING - Memory usage above 85%")
            elif usage_pct >= 75:
                print("  Status: 🟠 CAUTION - Memory usage above 75%")
            else:
                print("  Status: 🟢 HEALTHY")
        else:
            print("  Max Memory: Not configured")
            print("  Status: 🟡 WARNING - No memory limit set")

        fragmentation = memory.get("mem_fragmentation_ratio", 1.0)
        print(f"  Fragmentation Ratio: {fragmentation:.2f}")
        if fragmentation > 1.5:
            print("  Fragmentation: 🟡 HIGH - Consider memory defragmentation")
        print()

    # Performance metrics
    performance = diagnostics.get("performance", {})
    if performance and "error" not in performance:
        print("PERFORMANCE:")
        hits = performance.get("keyspace_hits", 0)
        misses = performance.get("keyspace_misses", 0)
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0

        print(f"  Ops/Sec: {performance.get('instantaneous_ops_per_sec', 0)}")
        print(f"  Total Commands: {performance.get('total_commands_processed', 0):,}")
        print(f"  Hit Rate: {hit_rate:.1f}% ({hits:,} hits, {misses:,} misses)")
        print(f"  Expired Keys: {performance.get('expired_keys', 0):,}")
        print(f"  Evicted Keys: {performance.get('evicted_keys', 0):,}")

        if performance.get("evicted_keys", 0) > 0:
            print("  Evictions: 🟡 Keys being evicted - check memory pressure")
        print()

    # Client connections
    clients = diagnostics.get("clients", {})
    if clients and "error" not in clients:
        print("CLIENTS:")
        print(f"  Connected Clients: {clients.get('connected_clients', 0)}")
        print(f"  Blocked Clients: {clients.get('blocked_clients', 0)}")

        client_connections = clients.get("client_connections", [])
        if client_connections:
            idle_long = len([c for c in client_connections if c.get("idle_seconds", 0) > 300])
            print(f"  Long Idle Connections (>5min): {idle_long}")

            if idle_long > 10:
                print("  Idle Connections: 🟡 Many long-idle connections detected")
        print()

    # Slowlog
    slowlog = diagnostics.get("slowlog", {})
    if slowlog and "error" not in slowlog:
        print("SLOWLOG:")
        print(f"  Slowlog Length: {slowlog.get('slowlog_length', 0)}")

        entries = slowlog.get("slowlog_entries", [])
        if entries:
            print(f"  Recent Slow Queries: {len(entries)}")

            # Show top slow commands
            recent_entries = entries[:3]
            for i, entry in enumerate(recent_entries, 1):
                duration_ms = entry.get("duration_microseconds", 0) / 1000
                print(f"    {i}. {entry.get('command', 'Unknown')} - {duration_ms:.1f}ms")

            if len(entries) > 10:
                print("  Slowlog: 🟡 Many slow queries detected - investigate performance")
        print()

    # Configuration alerts
    config = diagnostics.get("configuration", {})
    if config and "error" not in config:
        print("CONFIGURATION ALERTS:")
        alerts = []

        if not config.get("maxmemory"):
            alerts.append("🟡 No maxmemory limit configured")

        if config.get("maxmemory_policy") == "noeviction":
            alerts.append("🟠 Eviction policy set to 'noeviction' - may cause OOM")

        if config.get("appendonly") == "no" and not config.get("save"):
            alerts.append("🔴 No persistence configured - data loss risk")

        slowlog_threshold = config.get("slowlog_log_slower_than")
        if slowlog_threshold and int(slowlog_threshold) > 100000:  # 100ms
            alerts.append("🟡 Slowlog threshold >100ms - may miss performance issues")

        if alerts:
            for alert in alerts:
                print(f"  {alert}")
        else:
            print("  🟢 No configuration alerts")
        print()

    print("=" * 60)


async def main():
    """Main diagnostic capture function."""
    parser = argparse.ArgumentParser(
        description="Capture Redis diagnostic data for SRE analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--sections",
        nargs="*",
        choices=[
            "memory",
            "performance",
            "clients",
            "slowlog",
            "configuration",
            "keyspace",
            "replication",
            "persistence",
            "cpu",
        ],
        help="Diagnostic sections to capture (default: all)",
    )

    parser.add_argument("--output", "-o", type=str, help="Output file path (JSON format)")

    parser.add_argument("--redis-url", type=str, help="Redis connection URL (default: from config)")

    parser.add_argument("--summary", action="store_true", help="Display summary of key metrics")

    parser.add_argument("--raw", action="store_true", help="Include raw Redis INFO output")

    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress output except errors")

    args = parser.parse_args()

    try:
        # Capture diagnostics
        if not args.quiet:
            print("Capturing Redis diagnostics...")

        diagnostic_data = await capture_redis_diagnostics(
            sections=args.sections, redis_url=args.redis_url, include_raw_data=args.raw
        )

        # Check capture status
        if diagnostic_data.get("capture_status") != "success":
            print(
                f"ERROR: Diagnostic capture failed: {diagnostic_data.get('diagnostics', {}).get('error', 'Unknown error')}"
            )
            return 1

        # Save to file if requested
        if args.output:
            with open(args.output, "w") as f:
                json.dump(diagnostic_data, f, indent=2, default=str)
            if not args.quiet:
                print(f"Diagnostics saved to: {args.output}")

        # Display summary if requested or no output file specified
        if args.summary or (not args.output and not args.quiet):
            display_summary(diagnostic_data)

        # Print raw JSON if no other output and not quiet
        if not args.summary and not args.output and not args.quiet:
            print("\nRAW DIAGNOSTIC DATA:")
            print(json.dumps(diagnostic_data, indent=2, default=str))

        return 0

    except Exception as e:
        print(f"ERROR: Failed to capture diagnostics: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
