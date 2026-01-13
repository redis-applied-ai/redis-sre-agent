#!/bin/bash
#
# Benchmark script to measure cache speedup for tool calls.
#
# Usage:
#   ./scripts/benchmark_cache.sh [instance_id] [query]
#
# Example:
#   ./scripts/benchmark_cache.sh my-redis-instance "What is the memory usage?"
#
# This script runs the same query twice and compares timing.
# First run populates the cache, second run should be faster.

set -e

# Defaults
INSTANCE_ID="${1:-}"
QUERY="${2:-What is the current memory usage and configuration?}"
AGENT="${3:-chat}"  # Use chat agent for faster iteration

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Cache Speedup Benchmark${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ -z "$INSTANCE_ID" ]; then
    echo -e "${YELLOW}No instance ID provided. Listing available instances...${NC}"
    uv run redis-sre-agent instance list
    echo ""
    echo -e "${RED}Usage: $0 <instance_id> [query]${NC}"
    exit 1
fi

echo -e "${YELLOW}Instance:${NC} $INSTANCE_ID"
echo -e "${YELLOW}Query:${NC} $QUERY"
echo -e "${YELLOW}Agent:${NC} $AGENT"
echo ""

# Clear cache before benchmark (if cache CLI exists)
echo -e "${BLUE}--- Clearing cache (if available) ---${NC}"
uv run redis-sre-agent cache clear --instance "$INSTANCE_ID" 2>/dev/null || echo "(cache clear not yet implemented)"
echo ""

# First run - cold cache
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Run 1: Cold Cache${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

START1=$(python3 -c 'import time; print(time.time())')
uv run redis-sre-agent query "$QUERY" -r "$INSTANCE_ID" -a "$AGENT" > /tmp/benchmark_run1.txt 2>&1
END1=$(python3 -c 'import time; print(time.time())')
TIME1=$(python3 -c "print(f'{$END1 - $START1:.2f}')")

echo -e "${GREEN}Run 1 completed in ${TIME1}s${NC}"
echo ""

# Brief pause
sleep 1

# Second run - warm cache
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Run 2: Warm Cache${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

START2=$(python3 -c 'import time; print(time.time())')
uv run redis-sre-agent query "$QUERY" -r "$INSTANCE_ID" -a "$AGENT" > /tmp/benchmark_run2.txt 2>&1
END2=$(python3 -c 'import time; print(time.time())')
TIME2=$(python3 -c "print(f'{$END2 - $START2:.2f}')")

echo -e "${GREEN}Run 2 completed in ${TIME2}s${NC}"
echo ""

# Calculate speedup
SPEEDUP=$(python3 -c "
t1, t2 = $TIME1, $TIME2
if t2 > 0:
    speedup = (t1 - t2) / t1 * 100
    print(f'{speedup:.1f}')
else:
    print('N/A')
")

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "  Run 1 (cold): ${YELLOW}${TIME1}s${NC}"
echo -e "  Run 2 (warm): ${YELLOW}${TIME2}s${NC}"
echo -e "  Speedup:      ${GREEN}${SPEEDUP}%${NC}"
echo ""

# Show cache stats (if available)
echo -e "${BLUE}--- Cache Stats ---${NC}"
uv run redis-sre-agent cache stats --instance "$INSTANCE_ID" 2>/dev/null || echo "(cache stats not yet implemented)"
echo ""

# Optionally show truncated output
if [ "${SHOW_OUTPUT:-}" = "1" ]; then
    echo -e "${BLUE}--- Run 1 Output (first 20 lines) ---${NC}"
    head -20 /tmp/benchmark_run1.txt
    echo ""
    echo -e "${BLUE}--- Run 2 Output (first 20 lines) ---${NC}"
    head -20 /tmp/benchmark_run2.txt
fi

echo -e "${BLUE}Full output saved to /tmp/benchmark_run1.txt and /tmp/benchmark_run2.txt${NC}"
