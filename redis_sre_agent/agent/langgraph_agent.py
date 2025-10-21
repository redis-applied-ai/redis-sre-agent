"""LangGraph-based SRE Agent implementation.

This module implements a LangGraph workflow for SRE operations, providing
multi-turn conversation handling, tool calling integration, and state management.

TODO: The LangGraph agent doesn't use various features of LangGraph that it
could benefit from (mostly due to haste):
- ToolNode
- Conditional edges
- Sub-agents
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict
from urllib.parse import urlparse
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from ..api.instances import (
    create_instance_programmatically,
    get_instances_from_redis,
    save_instances_to_redis,
)
from ..core.config import settings
from ..tools.manager import ToolManager

logger = logging.getLogger(__name__)


def _extract_operation_from_tool_name(tool_name: str) -> str:
    """Extract human-readable operation name from full tool name.

    Tool names follow the format: {provider}_{hash}_{operation}
    Example: re_admin_ffffa3_get_cluster_info -> get_cluster_info

    Args:
        tool_name: Full tool name with provider, hash, and operation

    Returns:
        Operation name (e.g., "get_cluster_info")
    """
    import re

    # Match pattern: underscore + 6 hex chars + underscore + operation
    match = re.search(r"_([0-9a-f]{6})_(.+)$", tool_name)
    if match:
        return match.group(2)  # Return the operation part

    # Fallback: return the full name
    return tool_name


def _parse_redis_connection_url(connection_url: str) -> tuple[str, int]:
    """Parse Redis connection URL to extract host and port."""
    try:
        parsed = urlparse(connection_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        return host, port
    except Exception as e:
        masked_url = _mask_redis_url_credentials(connection_url)
        logger.warning(f"Failed to parse connection URL {masked_url}: {e}")
        return "localhost", 6379


def _get_secret_value(secret: Any) -> str:
    """Extract secret value from SecretStr or return plain string.

    Handles both SecretStr (from Pydantic) and plain str (after decryption).
    """
    if hasattr(secret, "get_secret_value"):
        return secret.get_secret_value()
    return str(secret)


def _mask_redis_url_credentials(url: str) -> str:
    """Mask username and password in Redis URL for safe logging/LLM usage.

    Args:
        url: Redis connection URL (e.g., redis://user:pass@host:port/db)

    Returns:
        Masked URL (e.g., redis://***:***@host:port/db)
    """
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            # Reconstruct URL with masked credentials
            masked_netloc = parsed.hostname or ""
            if parsed.port:
                masked_netloc += f":{parsed.port}"
            if parsed.username or parsed.password:
                masked_netloc = f"***:***@{masked_netloc}"

            masked_url = f"{parsed.scheme}://{masked_netloc}{parsed.path}"
            if parsed.query:
                masked_url += f"?{parsed.query}"
            if parsed.fragment:
                masked_url += f"#{parsed.fragment}"
            return masked_url
        return url
    except Exception as e:
        logger.warning(f"Failed to mask URL credentials: {e}")
        return "redis://***:***@<host>:<port>"


async def _detect_instance_type_with_llm(instance: Any, llm: Optional[ChatOpenAI] = None) -> str:
    """Use LLM to detect Redis instance type from metadata.

    Analyzes connection URL, description, notes, usage, and other metadata
    to determine if this is redis_enterprise, oss_cluster, oss_single, or redis_cloud.

    Args:
        instance: RedisInstance with metadata to analyze
        llm: Optional LLM to use (creates one if not provided)

    Returns:
        Detected instance type: 'redis_enterprise', 'oss_cluster', 'oss_single', 'redis_cloud', or 'unknown'
    """

    # Create LLM if not provided
    if llm is None:
        llm = ChatOpenAI(
            model=settings.model_name,
            temperature=0,  # Deterministic for classification
            api_key=settings.openai_api_key,
        )

    # Build analysis prompt with all available metadata
    # Extract secret value from SecretStr (or plain str after decryption)
    connection_url_str = _get_secret_value(instance.connection_url)
    parsed_url = urlparse(connection_url_str)
    port = parsed_url.port or 6379
    hostname = parsed_url.hostname or "unknown"

    # Mask credentials in URL before sending to LLM
    masked_url = _mask_redis_url_credentials(connection_url_str)

    prompt = f"""Analyze this Redis instance metadata and determine its type.

Instance Metadata:
- Name: {instance.name}
- Connection URL: {masked_url}
- Hostname: {hostname}
- Port: {port}
- Environment: {instance.environment}
- Usage: {instance.usage}
- Description: {instance.description}
- Notes: {instance.notes or "None"}

Instance Type Definitions:
1. **redis_enterprise**: Redis Enterprise Software or Redis Enterprise Cloud
   - Indicators: "enterprise" in name/description/notes, port 12000-12999, hostname contains "redis-enterprise"
   - Has cluster management, admin API, advanced features

2. **oss_cluster**: Open Source Redis Cluster (multi-node)
   - Indicators: "cluster" in name/description/notes, multiple nodes mentioned
   - Uses Redis Cluster protocol

3. **oss_single**: Open Source Redis (single node)
   - Indicators: standard port 6379, no cluster/enterprise mentions
   - Basic standalone Redis

4. **redis_cloud**: Managed Redis services (AWS ElastiCache, Redis Cloud, etc.)
   - Indicators: cloud provider hostnames (amazonaws.com, redislabs.com, azure, gcp)
   - Managed service

Based on the metadata above, what is the most likely instance type?

Respond with ONLY ONE of these exact values:
- redis_enterprise
- oss_cluster
- oss_single
- redis_cloud
- unknown (if truly ambiguous)

Your response (one word only):"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        detected_type = response.content.strip().lower()

        # Validate response
        valid_types = ["redis_enterprise", "oss_cluster", "oss_single", "redis_cloud", "unknown"]
        if detected_type in valid_types:
            logger.info(
                f"LLM detected instance type '{detected_type}' for {instance.name} "
                f"(port={port}, usage={instance.usage})"
            )
            return detected_type
        else:
            logger.warning(
                f"LLM returned invalid instance type '{detected_type}', defaulting to 'unknown'"
            )
            return "unknown"

    except Exception as e:
        logger.error(f"Failed to detect instance type with LLM: {e}")
        return "unknown"


def _extract_instance_details_from_message(message: str) -> Optional[Dict[str, str]]:
    """Extract Redis instance connection details from a user message.

    Looks for patterns like:
    - redis://hostname:port
    - environment: production/staging/development
    - usage: cache/analytics/session/queue/custom

    Returns:
        Dictionary with extracted details or None if not enough info found
    """
    import re

    details = {}
    message_lower = message.lower()

    # Extract Redis URL (required)
    url_pattern = r"redis://[^\s]+"
    url_match = re.search(url_pattern, message, re.IGNORECASE)
    if url_match:
        details["connection_url"] = url_match.group(0)
    else:
        # No URL found - can't create instance
        return None

    # Extract environment (required)
    env_patterns = [
        (r"\benvironment[:\s]+(\w+)", 1),
        (r"\benv[:\s]+(\w+)", 1),
        (r"\b(production|staging|development|prod|stage|dev)\b", 0),
    ]
    for pattern, group in env_patterns:
        match = re.search(pattern, message_lower)
        if match:
            env = match.group(group if group > 0 else 1).lower()
            # Normalize environment names
            if env in ["prod", "production"]:
                details["environment"] = "production"
            elif env in ["stage", "staging"]:
                details["environment"] = "staging"
            elif env in ["dev", "development"]:
                details["environment"] = "development"
            else:
                details["environment"] = env
            break

    # Extract usage type (required)
    usage_patterns = [
        (r"\busage[:\s]+(\w+)", 1),
        (r"\btype[:\s]+(\w+)", 1),
        (r"\b(cache|analytics|session|queue|custom)\b", 0),
    ]
    for pattern, group in usage_patterns:
        match = re.search(pattern, message_lower)
        if match:
            usage = match.group(group if group > 0 else 1).lower()
            details["usage"] = usage
            break

    # Extract description (optional)
    desc_patterns = [
        r"description[:\s]+([^\n]+)",
        r"desc[:\s]+([^\n]+)",
    ]
    for pattern in desc_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            details["description"] = match.group(1).strip()
            break

    # Check if we have minimum required fields
    if "connection_url" in details and "environment" in details and "usage" in details:
        # Generate a name if not provided
        if "name" not in details:
            parsed = urlparse(details["connection_url"])
            host = parsed.hostname or "redis"
            details["name"] = f"{host}-{details['environment']}"

        # Add default description if not provided
        if "description" not in details:
            details["description"] = (
                "Redis instance created by agent from user-provided connection details"
            )

        return details

    return None


# SRE-focused system prompt
SRE_SYSTEM_PROMPT = """
You are an experienced Redis SRE who writes clear, actionable triage notes. You sound like a knowledgeable colleague sharing findings and recommendations - professional but conversational.

## Your Approach

When someone brings you a Redis issue, you:
1. **Look at the data first** - examine any diagnostic info they've provided
2. **Figure out what's actually happening** - separate symptoms from root causes
3. **Search your knowledge** when you need specific troubleshooting steps
4. **Give them a clear plan** - actionable steps they can take right now

## Writing Style

Write like you're updating a colleague on what you found. Use natural language:
- "I took a look at your Redis instance and here's what I'm seeing..."
- "The good news is..." / "The concerning part is..."
- "Let's start with..." / "Next, I'd recommend..."
- "Based on what I found in our runbooks..."

## Response Format (Use Proper Markdown)

Structure your response with clear headers and formatting:

# Initial Assessment
Brief summary of what you found

# What I'm Seeing
Key findings from diagnostics, with **bold** for important metrics

# My Recommendation
Clear action plan with:
- Numbered steps for immediate actions
- **Bold text** for critical items
- Code blocks for commands when helpful

# Supporting Info
- Where you got your recommendations (cite runbooks/docs)
- Key diagnostic evidence that supports your analysis

## Formatting Requirements

- Use `#` headers for main sections
- Use `**bold**` for emphasis on critical items
- Use `-` or `1.` for lists and action items
- Use code blocks with ``` for commands
- Add blank lines between paragraphs for readability
- Keep paragraphs short (2-3 sentences max)

## Command Guidance

- When you recommend steps that involve executing something, use real user-facing commands or API requests.
- Valid forms:
  - CLI commands (e.g., `redis-cli`, `uv run pytest`, `curl ...`)
  - HTTP requests with method, path, and minimal payload (include a `curl` example for REST APIs like Redis Enterprise Admin)
- Do NOT reference internal tool names like "run get_cluster_info" or "use list_nodes" — those are internal agent tools the user cannot run.
- If internal tools informed your findings, translate them to user-facing equivalents (e.g., show the corresponding REST endpoint and example `curl`).

## Keep It Practical

Focus on what they can do right now:
- Skip the theory - they need action steps
- Don't explain basic Redis concepts unless directly relevant
- Avoid generic advice like "monitor your metrics" - be specific
- If you're not sure about something, say so and suggest investigation steps

## Redis Enterprise Cluster Checks

**CRITICAL: Redis Enterprise databases are DIFFERENT from Redis Open Source**

When working with Redis Enterprise instances (instance_type: redis_enterprise), you MUST understand:

### What You CANNOT Do with Redis Enterprise
- ❌ **DO NOT suggest CONFIG SET for persistence, replication, or clustering** - these are managed by Redis Enterprise
- ❌ **DO NOT suggest BGSAVE, BGREWRITEAOF, or other persistence commands** - not supported
- ❌ **DO NOT suggest REPLICAOF or replication commands** - replication is automatic
- ❌ **DO NOT suggest MODULE LOAD** - modules are managed via Cluster Manager/API
- ❌ **DO NOT trust INFO output for configuration details** - it shows runtime state, not configuration
- ❌ **DO NOT suggest ACL SETUSER or ACL DELUSER** - ACL is managed via Cluster Manager/API

### What INFO Shows vs. Reality in Redis Enterprise
The `INFO` command output is MISLEADING for Redis Enterprise:
- `aof_enabled=1, aof_current_size=0` - This is NORMAL. Redis Enterprise manages AOF internally.
- `slave0: ip=0.0.0.0, port=0` - This is NORMAL. Replication is managed by Redis Enterprise, not visible via INFO.
- `maxmemory=0` - This is NORMAL. Memory limits are enforced at the cluster level, not visible via CONFIG GET.
- `rdb_changes_since_last_save` - This is NORMAL. RDB snapshots are managed by Redis Enterprise.

**DO NOT suggest "fixing" these - they are expected behavior in Redis Enterprise!**

### What You SHOULD Do with Redis Enterprise
1. **Use the Admin REST API for configuration details** - Call these tools to see actual configuration (refer to the
    Redis Enterprise Admin API tool descriptions to see all available tools):
   - `get_cluster_info` - Cluster-level information
   - `get_database` - Database configuration (memory limits, persistence, replication, clustering, modules, etc.)
   - `list_nodes` - Node status (check for maintenance mode: `accept_servers=false`)
   - `list_shards` - Shard distribution across nodes
   - `get_database_stats` - Database performance metrics
   - `get_node_stats` - Node-level metrics

2. **Use Redis commands for data operations only**:
   - ✅ DBSIZE, KEYS, SCAN - data inspection
   - ✅ SLOWLOG - query performance
   - ✅ CLIENT LIST - connection monitoring
   - ✅ MEMORY USAGE - key-level memory analysis
   - ✅ INFO stats, keyspace, clients - runtime metrics

3. **ALWAYS check cluster health**:
   - Call `get_cluster_info` to check overall cluster status
   - Call `list_nodes` to check if any nodes are in maintenance mode (`accept_servers=false`), failed, or degraded
   - Call `list_databases` and `get_database` to check database status and configuration
   - Call `list_shards` to check if shards are properly distributed across nodes

### Example: Correct Redis Enterprise Health Check

❌ **WRONG Approach:**
```
I see AOF is enabled but size is 0 - you should run BGREWRITEAOF.
I see a replica at 0.0.0.0:0 - your replication is broken.
You should set maxmemory with CONFIG SET.
```

✅ **CORRECT Approach:**
```
I checked your Redis Enterprise database via the Admin REST API. Here's what I found:

**Cluster Status (from get_cluster_info):**
- Cluster: production-cluster
- Nodes: 3 (all active)
- Total shards: 12

**Database Configuration (from get_database):**
- Memory: 246 MB used / 512 MB limit
- Persistence: aof-every-1-second (managed by Redis Enterprise)
- Replication: Enabled (1 replica per shard)
- Sharding: 2 shards
- Modules: RedisJSON 2.6, RedisSearch 2.8

**Node Status (from list_nodes):**
- All 3 nodes active
- No nodes in maintenance mode

**Runtime Metrics (from INFO):**
- Current ops/sec: 81
- Connected clients: 13
- Keys: 5,357 in db0
- No slow queries

**Assessment:**
Your database is healthy. The INFO output shows some confusing values (AOF size=0, replica at 0.0.0.0:0)
but these are normal for Redis Enterprise - persistence and replication are managed automatically by the platform.
```

**ALWAYS call get_database and get_cluster_info for Redis Enterprise instances to get accurate configuration!**

## Redis Cloud Management

**CRITICAL: Redis Cloud databases are DIFFERENT from Redis Open Source**

When working with Redis Cloud instances (instance_type: redis_cloud), you MUST understand:

### What You CANNOT Do with Redis Cloud
- ❌ **DO NOT suggest CONFIG SET for persistence, replication, or clustering** - these are managed by Redis Cloud
- ❌ **DO NOT suggest BGSAVE, BGREWRITEAOF, or other persistence commands** - not supported
- ❌ **DO NOT suggest REPLICAOF or replication commands** - replication is automatic
- ❌ **DO NOT suggest MODULE LOAD** - modules are managed via console/API
- ❌ **DO NOT trust INFO output for configuration details** - it shows runtime state, not configuration
- ❌ **DO NOT suggest ACL SETUSER or ACL DELUSER** - ACL is managed via console/API

### What INFO Shows vs. Reality in Redis Cloud
The `INFO` command output is MISLEADING for Redis Cloud:
- `aof_enabled=1, aof_current_size=0` - This is NORMAL. Redis Cloud manages AOF internally.
- `slave0: ip=0.0.0.0, port=0` - This is NORMAL. Replication is managed by Redis Cloud, not visible via INFO.
- `maxmemory=0` - This is NORMAL. Memory limits are enforced at the cluster level, not visible via CONFIG GET.
- `rdb_changes_since_last_save` - This is NORMAL. RDB snapshots are managed by Redis Cloud.

**DO NOT suggest "fixing" these - they are expected behavior in Redis Cloud!**

### What You SHOULD Do with Redis Cloud
1. **Use the REST API for configuration details** - Call `get_database` to see actual configuration:
   - Memory limits (`memoryUsedInMb`, `datasetSizeInGb`)
   - Persistence settings (`dataPersistence`)
   - Replication status (`replication`)
   - Clustering configuration (`clustering.numberOfShards`)
   - Security settings (`security.*`)
   - Module versions (`modules`)
   - Network endpoints (`publicEndpoint`, `privateEndpoint`)
   - Throughput limits (`throughputMeasurement`)

2. **Use Redis commands for data operations only**:
   - ✅ DBSIZE, KEYS, SCAN - data inspection
   - ✅ SLOWLOG - query performance
   - ✅ CLIENT LIST - connection monitoring
   - ✅ MEMORY USAGE - key-level memory analysis
   - ✅ INFO stats, keyspace, clients - runtime metrics

3. **Available Cloud Management Tools**:
See the Redis Cloud API tool descriptions for more, but a summary is:
   - `get_account` - View account details
   - `get_regions` - List available regions
   - `list_subscriptions` - List all subscriptions
   - `get_subscription` - Get subscription details
   - `list_databases` - List databases in a subscription
   - `get_database` - **USE THIS for database configuration details**
   - `list_users` - View account users
   - `list_tasks` - Monitor async operations

### Example: Correct Redis Cloud Health Check

❌ **WRONG Approach:**
```
I see AOF is enabled but size is 0 - you should run BGREWRITEAOF.
I see a replica at 0.0.0.0:0 - your replication is broken.
You should set maxmemory with CONFIG SET.
```

✅ **CORRECT Approach:**
```
I checked your Redis Cloud database via the REST API. Here's what I found:

**Configuration (from REST API):**
- Memory: 246 MB used / 512 MB limit
- Persistence: snapshot-every-1-hour (managed by Redis Cloud)
- Replication: Enabled with automatic failover
- Clustering: 2 shards
- Throughput: 2500 ops/sec limit

**Runtime Metrics (from INFO):**
- Current ops/sec: 81 (well below limit)
- Connected clients: 13
- Keys: 5,357 in db0
- No slow queries

**Assessment:**
Your database is healthy. The INFO output shows some confusing values (AOF size=0, replica at 0.0.0.0:0)
but these are normal for Redis Cloud - persistence and replication are managed automatically by the platform.
```

**ALWAYS call get_database for Redis Cloud instances to get accurate configuration!**

**CRITICAL: Understanding Node Shard Counts and Maintenance Mode**

When you see a node with `shard_count: 0` or `accept_servers: false` in list_nodes output:
- **This means the node is in MAINTENANCE MODE**
- Maintenance mode is used for upgrades, hardware maintenance, or troubleshooting
- The node is NOT serving traffic and shards have been migrated off
- **You MUST explain this clearly in your Initial Assessment** - don't bury it in recommendations

**How to communicate this to the user:**

❌ DON'T say: "Node 2 is idle" or "Node 2 cannot host shards"
✅ DO say: "Node 2 is in maintenance mode - it's been taken out of service intentionally"

❌ DON'T treat it as an optimization: "Fix Node 2 if you intend to use all three nodes"
✅ DO explain the situation: "Node 2 is in maintenance mode. This is typically done for upgrades or maintenance. If the maintenance is complete, you should exit maintenance mode to restore full cluster capacity."

**Example Initial Assessment:**
```
⚠️ Node 2 is in maintenance mode

I can see that Node 2 has shard_count=0 and accept_servers=false, which means it's been
placed in maintenance mode. This is a deliberate action - someone ran `rladmin node 2
maintenance_mode on` to take it out of service (usually for upgrades or hardware work).

While in maintenance mode:
- Node 2 is not serving any traffic
- All shards have been migrated to other nodes
- Your cluster is running on reduced capacity (2 nodes instead of 3)

If the maintenance is complete, you should exit maintenance mode with:
`rladmin node 2 maintenance_mode off`
```

**What to check:**
- `accept_servers: false` → Node is in maintenance mode
- `shard_count: 0` → Shards have been migrated off
- `max_listeners: 0` → Node is not accepting new connections

**What to recommend:**
1. First, explain that the node is in maintenance mode and what that means
2. Ask if maintenance is complete
3. If yes, provide the command to exit: `rladmin node <id> maintenance_mode off`
4. Warn about reduced capacity and availability risk

**Other key indicators of problems:**
- Databases in "active-change-pending" status → Configuration change in progress
- Cluster alerts → Check get_cluster_alerts for active warnings
- Uneven shard distribution (excluding maintenance nodes) → Potential performance issues

## When to Search Knowledge Base

Look up specific troubleshooting steps and reference documentation whenever
you're not sure about the best course of action. For example:
- Connection limit issues → search "connection limit troubleshooting"
- Memory problems → search "memory optimization" or "eviction policy"
- Performance issues → search "slow query analysis" or "latency troubleshooting"
- Security concerns → search "Redis security configuration"
- Redis CLI commands for JSoN → search "redis-cli commands docs json"
- rladmin commands for maintenance mode → search "rladmin CLI reference maintenance mode"

## Understanding Usage Patterns

Search for immediate remediation steps based on the identified problem category:
- **Connection Issues**: "Redis connection limit troubleshooting", "client timeout resolution"
- **Memory Issues**: "Redis memory optimization", "eviction policy configuration"
- **Performance Issues**: "Redis slow query analysis", "performance optimization"
- **Configuration Issues**: "Redis security configuration", "operational best practices"
- **Search by symptoms**: Use specific metrics and error patterns you discover

When you're trying to figure out how Redis is being used, look for clues but don't be too definitive. Usage patterns aren't always clear-cut.

**Signs it might be used as a cache:**
- Most keys have TTLs set (high expires/keys ratio)
- Lots of keys expiring regularly
- Eviction policies are set up
- Key names look like session IDs or temp data

**Signs it might be persistent storage:**
- Few or no TTLs on keys (low expires/keys ratio)
- Very few keys expiring
- `noeviction` policy to prevent data loss
- Key names look like user data or business entities

Redis usage patterns must be inferred from multiple signals - persistence/backup
settings alone are insufficient. Always express your analysis as **likely patterns**
rather than definitive conclusions, and acknowledge the uncertainty inherent in
pattern detection.

**When it's unclear:**
- Mixed TTL patterns could mean hybrid usage
- Persistence enabled with high TTL coverage might be cache with backup
- No clear pattern? Focus on the immediate problem rather than guessing

**How to talk about it:**
- "Based on what I'm seeing, this looks like..."
- "The data suggests this might be..."
- "I can't tell for sure, but it appears to be..."
- When in doubt: "Let's focus on the immediate issue first"

## Source Citation Requirements

**ALWAYS CITE YOUR SOURCES** when referencing information from search results:
- When you use search_knowledge_base, cite the source document and title
- Format citations as: "According to [Document Title] (source: [source_path])"
- For runbooks, indicate document type: "Based on the runbook: [Title]"
- For documentation, indicate document type: "From Redis documentation: [Title]"
- Include severity level when relevant: "[Title] (severity: critical)"
- When combining information from multiple sources, cite each one

**Example citations:**
- "According to Redis Connection Limit Exceeded Troubleshooting (source: redis-connection-limit-exceeded.md), the immediate steps are..."
- "Based on the runbook: Redis Memory Fragmentation Crisis (severity: high), you should..."
- "From Redis documentation: Performance Optimization Guide, the recommended approach is..."

Remember: You are responding to a live incident. Focus on immediate threats and actionable steps to prevent system failure.
"""

# Fact-checker system prompt
FACT_CHECKER_PROMPT = """You are a Redis technical fact-checker. Your role is to review SRE agent responses for factual accuracy about Redis concepts, metrics, operations, URLs, and command syntax.

## Your Task

Review the provided SRE agent response and identify any statements that are:
1. **Technically incorrect** about Redis internals, operations, or behavior
2. **Misleading interpretations** of Redis metrics or diagnostic data
3. **Unsupported claims** that lack evidence from the diagnostic data provided
4. **Contradictions** between stated facts and the actual data shown
5. **Invalid URLs** that return 404 errors or are inaccessible
6. **Invalid or fabricated commands** (especially `rladmin` for Redis Enterprise) or incorrect CLI syntax

## Common Redis Fact-Check Areas

- **Memory Operations**: Redis is entirely in-memory; no disk access for data retrieval
- **Usage Pattern Detection**: Must consider TTL coverage (`expires` vs `keys`), expiration activity (`expired_keys`), and maxmemory policies - not just AOF/RDB settings
- **Keyspace Hit Rate**: Measures key existence (hits) vs non-existence (misses), not memory vs disk
- **Replication**: Master/slave terminology, replication lag implications
- **Persistence**: RDB vs AOF, when disk I/O actually occurs
- **Eviction Policies**: How different policies work and when they trigger
- **Configuration**: Default values, valid options, and their implications
- **Command Validity**: Verify that any suggested shell/CLI commands (particularly `rladmin`) are real and use correct syntax per Redis Enterprise documentation; flag invented subcommands or options
- **Documentation URLs**: Verify that referenced URLs are valid and accessible


## CLI Command Validation
- For any CLI commands detected (e.g., `rladmin`, `redis-cli`), cross-check syntax against official Redis documentation.
- Prefer exact matches from documentation over inferred syntax.
- If documentation cannot be found for a suggested command, treat it as invalid and flag it.
- Cite sources when confirming command syntax.

## Cross-checking Redis Documentation
- You have access to knowledge search
- Use `search_knowledge_base` tool to verify facts, command syntax, and URLs

## Response Format

If you find factual errors, invalid commands, or invalid URLs, respond with:
```json
{
  "has_errors": true,
  "errors": [
    {
      "claim": "exact text of the incorrect claim, invalid command, or invalid URL",
      "issue": "explanation of why it's wrong and, if possible, the correct alternative",
      "category": "redis_internals|metrics_interpretation|configuration|invalid_command|invalid_url|other"
    }
  ],
  "suggested_research": [
    "specific topics the agent should research to correct the errors (e.g., 'rladmin database command syntax')"
  ],
  "url_validation_performed": true
}
```

If no errors are found, respond with:
```json
{
  "has_errors": false,
  "validation_notes": "brief note about what was verified (concepts, commands, URLs)",
  "url_validation_performed": true
}
```

Be strict but fair - flag clear technical inaccuracies, invented CLI commands, and broken URLs, not minor wording choices or style preferences.
"""


class AgentState(TypedDict):
    """State schema for the SRE LangGraph agent."""

    messages: List[BaseMessage]
    session_id: str
    user_id: str
    current_tool_calls: List[Dict[str, Any]]
    iteration_count: int
    max_iterations: int
    instance_context: Optional[Dict[str, Any]]  # For Redis instance context


class SREToolCall(BaseModel):
    """Model for SRE tool call requests."""

    tool_name: str = Field(..., description="Name of the SRE tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    tool_call_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique tool call ID"
    )


# TODO: Break this out into functions.
# TODO: Researcher, Safety Evaluator, and Fact-checker should be individual nodes
#       with conditional edges and/or sub-agents.
class SRELangGraphAgent:
    """LangGraph-based SRE Agent with multi-turn conversation and tool calling."""

    def __init__(self, progress_callback=None):
        """Initialize the SRE LangGraph agent."""
        self.settings = settings
        self.progress_callback = progress_callback
        # Single LLM with both reasoning and function calling capabilities
        self.llm = ChatOpenAI(
            model=self.settings.openai_model,
            openai_api_key=self.settings.openai_api_key,
        )

        # Tools will be loaded per-query using ToolManager
        # No tools bound at initialization - they're bound per conversation
        self.llm_with_tools = self.llm  # Will be rebound with tools per query

        # Workflow will be built per-query with the appropriate ToolManager
        # Note: We create a new MemorySaver for each query to ensure proper isolation
        # This prevents cross-contamination between different tasks/threads

        logger.info("SRE LangGraph agent initialized (tools loaded per-query)")

    async def _resolve_instance_redis_url(self, instance_id: str) -> Optional[str]:
        """Resolve instance ID to Redis URL using connection_url from instance data.

        IMPORTANT: This method returns None if the instance cannot be found.
        It NEVER falls back to settings.redis_url (the application database).
        Tools must handle None and fail gracefully rather than connecting to the wrong database.
        """
        try:
            instances = await get_instances_from_redis()
            for instance in instances:
                if instance.id == instance_id:
                    # Return the secret value for internal use
                    return _get_secret_value(instance.connection_url)

            logger.error(
                f"Instance {instance_id} not found. "
                "NOT falling back to application database - tools must fail gracefully."
            )
            return None
        except Exception as e:
            logger.error(
                f"Failed to resolve instance {instance_id}: {e}. "
                "NOT falling back to application database - tools must fail gracefully."
            )
            return None

    def _build_workflow(
        self, tool_mgr: ToolManager, target_instance: Optional[Any] = None
    ) -> StateGraph:
        """Build the LangGraph workflow for SRE operations.

        Args:
            tool_mgr: ToolManager instance for resolving tool calls
            target_instance: Optional RedisInstance for context-specific prompts
        """

        async def agent_node(state: AgentState) -> AgentState:
            """Main agent node that processes user input and decides on tool calls."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            # max_iterations = state.get("max_iterations", 10)  # Not used in this function

            # Add system message if this is the first interaction
            if len(messages) == 1 and isinstance(messages[0], HumanMessage):
                system_prompt = SRE_SYSTEM_PROMPT

                # Add Redis Cloud-specific context if working with a cloud instance
                if target_instance and target_instance.instance_type == "redis_cloud":
                    redis_cloud_context = """

## CRITICAL REDIS CLOUD CONTEXT

You are working with a **Redis Cloud** database. Redis Cloud is FUNDAMENTALLY DIFFERENT from Redis Open Source.

### DO NOT Trust INFO Output for Configuration
The INFO command shows RUNTIME STATE, not CONFIGURATION. These are NORMAL and EXPECTED in Redis Cloud:
- `aof_enabled=1, aof_current_size=0` - AOF is managed internally by Redis Cloud
- `slave0: ip=0.0.0.0, port=0` - Replication is managed by Redis Cloud (not visible via INFO)
- `maxmemory=0` - Memory limits are enforced at cluster level (not visible via CONFIG GET)
- `rdb_changes_since_last_save` - RDB snapshots are managed by Redis Cloud

**STOP suggesting "fixes" for these - they are NOT problems!**

### What You MUST Do First
1. **Call `get_database` tool** to get the ACTUAL database configuration from the REST API
2. This returns the REAL configuration: memory limits, persistence settings, replication status, clustering, security, modules, endpoints, throughput limits
3. Use INFO only for runtime metrics (ops/sec, connected clients, keyspace stats)

### What You CANNOT Suggest
- ❌ CONFIG SET for persistence, replication, clustering, maxmemory
- ❌ BGSAVE, BGREWRITEAOF, or other persistence commands
- ❌ REPLICAOF or replication commands
- ❌ MODULE LOAD
- ❌ ACL SETUSER or ACL DELUSER
- ❌ "Fix" AOF size=0 or replica at 0.0.0.0:0

### Correct Diagnostic Approach
1. Call `get_database` to get configuration from REST API
2. Use INFO for runtime metrics only
3. Compare actual usage vs. configured limits
4. Provide recommendations based on ACTUAL configuration, not INFO output

**Remember: Redis Cloud manages persistence, replication, clustering, and modules automatically. Use the REST API to see the real configuration!**
"""
                    system_prompt += redis_cloud_context

                # Add Redis Enterprise-specific context if working with an enterprise instance
                elif target_instance and target_instance.instance_type == "redis_enterprise":
                    redis_enterprise_context = """

## CRITICAL REDIS ENTERPRISE CONTEXT

You are working with a **Redis Enterprise** database. Redis Enterprise is FUNDAMENTALLY DIFFERENT from Redis Open Source.

### DO NOT Trust INFO Output for Configuration
The INFO command shows RUNTIME STATE, not CONFIGURATION. These are NORMAL and EXPECTED in Redis Enterprise:
- `aof_enabled=1, aof_current_size=0` - AOF is managed internally by Redis Enterprise
- `slave0: ip=0.0.0.0, port=0` - Replication is managed by Redis Enterprise (not visible via INFO)
- `maxmemory=0` - Memory limits are enforced at cluster level (not visible via CONFIG GET)
- `rdb_changes_since_last_save` - RDB snapshots are managed by Redis Enterprise

**STOP suggesting "fixes" for these - they are NOT problems!**

### What You MUST Do First
1. **Call `get_cluster_info` tool** to check overall cluster health
2. **Call `get_database` tool** to get the ACTUAL database configuration from the Admin REST API
3. **Call `list_nodes` tool** to check node status (especially maintenance mode: `accept_servers=false`)
4. **Call `list_shards` tool** to check shard distribution
5. Use INFO only for runtime metrics (ops/sec, connected clients, keyspace stats)

### What You CANNOT Suggest
- ❌ CONFIG SET for persistence, replication, clustering, maxmemory
- ❌ BGSAVE, BGREWRITEAOF, or other persistence commands
- ❌ REPLICAOF or replication commands
- ❌ MODULE LOAD
- ❌ ACL SETUSER or ACL DELUSER
- ❌ "Fix" AOF size=0 or replica at 0.0.0.0:0

### Correct Diagnostic Approach
1. Call `get_cluster_info` to check cluster health
2. Call `list_nodes` to check for nodes in maintenance mode or degraded state
3. Call `get_database` to get database configuration from Admin REST API
4. Call `list_shards` to check shard distribution
5. Use INFO for runtime metrics only
6. Compare actual usage vs: configured limits
7. Provide recommendations based on ACTUAL configuration, not INFO output

### Critical: Check for Maintenance Mode
Nodes with `accept_servers=false` are in MAINTENANCE MODE and won't accept new shards. This is a common cause of issues!

**Remember: Redis Enterprise manages persistence, replication, clustering, and modules automatically. Use the Admin REST API to see the real configuration!**

### CLI Command Guidance (rladmin)
- Never invent or guess rladmin subcommands. Examples that DO NOT EXIST: `rladmin list databases`, `rladmin get database name <db>`, `rladmin list shards`, `rladmin get database stats`.
- Before suggesting any rladmin command, use the `search_knowledge_base` tool to find the exact syntax in the Redis Enterprise documentation and cite the source.
- Prefer the Admin REST API tools available to you (`get_cluster_info`, `get_database`, `list_nodes`, `list_shards`). Do NOT turn tool names into CLI commands.
- If you cannot find a documented rladmin command for the task, omit CLI suggestions and stick to Admin REST API guidance.
"""
                    system_prompt += redis_enterprise_context

                system_message = AIMessage(content=system_prompt)
                messages = [system_message] + messages

            # Generate response with tool calling capability using retry logic
            async def _agent_llm_call():
                """Inner function for agent LLM call with retry logic."""
                return await self.llm_with_tools.ainvoke(messages)

            try:
                response = await self._retry_with_backoff(
                    _agent_llm_call,
                    max_retries=self.settings.llm_max_retries,
                    initial_delay=self.settings.llm_initial_delay,
                    backoff_factor=self.settings.llm_backoff_factor,
                )
                logger.debug("Agent LLM call successful after potential retries")
            except Exception as e:
                logger.error(f"Agent LLM call failed after all retries: {str(e)}")
                # Fallback response to prevent workflow failure
                response = AIMessage(
                    content="I apologize, but I'm experiencing technical difficulties processing your request. Please try again in a moment."
                )

            # Update state
            new_messages = messages + [response]
            state["messages"] = new_messages
            state["iteration_count"] = iteration_count + 1

            # Track tool calls if any
            if hasattr(response, "tool_calls") and response.tool_calls:
                state["current_tool_calls"] = [
                    {
                        "tool_call_id": tc.get("id", str(uuid4())),
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    }
                    for tc in response.tool_calls
                ]
                logger.info(f"Agent requested {len(response.tool_calls)} tool calls")
            else:
                state["current_tool_calls"] = []

            return state

        async def tool_node(state: AgentState) -> AgentState:
            """Execute SRE tools and return results."""
            messages = state["messages"]
            tool_calls = state.get("current_tool_calls", [])

            tool_messages = []

            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_call_id = tool_call["tool_call_id"]

                logger.info(f"Executing SRE tool: {tool_name} with args: {tool_args}")

                # Send a single, meaningful status update about what the agent is doing
                if self.progress_callback:
                    # Prefer provider-supplied status update; fall back to generic
                    status_msg = tool_mgr.get_status_update(
                        tool_name, tool_args
                    ) or self._generate_tool_reflection(tool_name, tool_args)
                    if status_msg:
                        await self.progress_callback(status_msg, "agent_reflection")

                try:
                    # Use ToolManager to resolve and execute the tool call
                    logger.info(f"Executing tool {tool_name} with args: {tool_args}")

                    result = await tool_mgr.resolve_tool_call(tool_name, tool_args)

                    # Emit fragment/source metadata for knowledge searches
                    try:
                        if (
                            self.progress_callback
                            and isinstance(result, dict)
                            and isinstance(tool_name, str)
                            and tool_name.startswith("knowledge_")
                            and tool_name.endswith("_search")
                        ):
                            items = result.get("results") or []
                            fragments = []
                            for doc in items:
                                try:
                                    fragments.append(
                                        {
                                            "id": doc.get("id"),
                                            "document_hash": doc.get("document_hash"),
                                            "chunk_index": doc.get("chunk_index"),
                                            "title": doc.get("title"),
                                            "source": doc.get("source"),
                                        }
                                    )
                                except Exception:
                                    pass
                            if fragments:
                                await self.progress_callback(
                                    "Retrieved knowledge fragments",
                                    "knowledge_sources",
                                    {"fragments": fragments},
                                )
                    except Exception:
                        # Best-effort: do not fail tool execution due to progress metadata errors
                        pass

                    # Format result as a readable string
                    if isinstance(result, dict):
                        formatted_result = json.dumps(result, indent=2, default=str)
                        tool_content = f"Tool '{tool_name}' executed successfully.\n\nResult:\n{formatted_result}"
                    else:
                        tool_content = (
                            f"Tool '{tool_name}' executed successfully.\nResult: {result}"
                        )

                except Exception as e:
                    tool_content = f"Error executing tool '{tool_name}': {str(e)}"
                    logger.error(f"Tool execution error for {tool_name}: {str(e)}")

                # Create tool message
                tool_message = ToolMessage(content=tool_content, tool_call_id=tool_call_id)
                tool_messages.append(tool_message)

            # Update messages with tool results
            state["messages"] = messages + tool_messages
            state["current_tool_calls"] = []  # Clear tool calls

            return state

        async def reasoning_node(state: AgentState) -> AgentState:
            """Final reasoning node using O1 model for better analysis."""
            messages = state["messages"]

            # Build conversation history with clear turn structure
            conversation_turns = []
            tool_results = []
            current_turn_user_msg = None
            current_turn_assistant_msg = None
            turn_number = 0

            for msg in messages:
                if isinstance(msg, HumanMessage):
                    # If we have a previous turn, save it
                    if current_turn_user_msg:
                        turn_number += 1
                        turn_text = f"**Turn {turn_number}:**\nUser: {current_turn_user_msg}"
                        if current_turn_assistant_msg:
                            turn_text += f"\nAssistant: {current_turn_assistant_msg}"
                        conversation_turns.append(turn_text)

                    # Start new turn
                    current_turn_user_msg = msg.content
                    current_turn_assistant_msg = None

                elif isinstance(msg, AIMessage):
                    # Skip system messages (they start with "You are")
                    if not msg.content.startswith("You are"):
                        current_turn_assistant_msg = msg.content

                elif isinstance(msg, ToolMessage):
                    tool_results.append(f"Tool Data: {msg.content}")

            # Add the final turn (current question)
            if current_turn_user_msg:
                turn_number += 1
                turn_text = f"**Turn {turn_number} (Current):**\nUser: {current_turn_user_msg}"
                if current_turn_assistant_msg:
                    turn_text += f"\nAssistant: {current_turn_assistant_msg}"
                conversation_turns.append(turn_text)

            # Build the prompt with clear structure
            conversation_history = (
                "\n\n".join(conversation_turns)
                if conversation_turns
                else "No previous conversation."
            )
            tool_data = "\n\n".join(tool_results) if tool_results else "No tool data available."

            # Determine if this is a follow-up question
            is_followup = turn_number > 1
            task_description = (
                "The user has asked a follow-up question. Based on the conversation history and tool results, "
                "provide a clear, direct answer to their latest question. Reference previous context when relevant."
                if is_followup
                else "You've been investigating a Redis issue. Based on your diagnostic work and tool results, "
                "write up your findings and recommendations like you're updating a colleague."
            )

            reasoning_prompt = f"""{SRE_SYSTEM_PROMPT}

## Conversation History

{conversation_history}

## Tool Results from Investigation

{tool_data}

## Your Task

{task_description}

## Response Guidelines

Write a natural, conversational response using proper markdown formatting. Include:

- **Clear headers** with `#` for main sections
- **Bold text** with `**` for critical findings and action items
- **Proper lists** with `-` for bullet points (ensure blank line before list and space after `-`)
- **Numbered lists** with `1.` for action steps (ensure blank line before list)
- **Code blocks** with ``` for any commands
- **Blank lines** between paragraphs and before/after lists for readability

**Critical formatting rules:**
- Always put a blank line before and after lists
- Use `- ` (dash + space) for bullet points
- Use `1. ` (number + period + space) for numbered lists
- Put blank lines between major sections

Sound like an experienced SRE sharing findings with a colleague. Be direct about what you found and what needs to happen next.

**Important**: Format numbers with commas (e.g., "4,950 keys" not "4 950 keys")."""

            try:
                # Use configured model for final analysis
                async def _reasoning_llm_call():
                    return await self.llm.ainvoke([HumanMessage(content=reasoning_prompt)])

                response = await self._retry_with_backoff(
                    _reasoning_llm_call,
                    max_retries=self.settings.llm_max_retries,
                    initial_delay=self.settings.llm_initial_delay,
                    backoff_factor=self.settings.llm_backoff_factor,
                )
                logger.debug("Reasoning LLM call successful")

            except Exception as e:
                logger.error(f"Reasoning LLM call failed after all retries: {str(e)}")
                # Fallback to a simple response
                response = AIMessage(
                    content="I apologize, but I encountered technical difficulties during analysis. Please try again or contact support."
                )

            # Update state with final reasoning response
            state["messages"] = messages + [response]
            return state

        def should_continue(state: AgentState) -> str:
            """Decide whether to continue with tools, reasoning, or end the conversation."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            max_iterations = state.get("max_iterations", settings.max_iterations)

            # Check iteration limit
            if iteration_count >= max_iterations:
                logger.warning(f"Reached max iterations ({max_iterations})")
                return "reasoning"  # Go to reasoning for final analysis

            # Check if the last message has tool calls
            if messages and hasattr(messages[-1], "tool_calls"):
                if messages[-1].tool_calls:
                    return "tools"

            # Check if we have pending tool calls in state
            if state.get("current_tool_calls"):
                return "tools"

            # If we've used tools and have no more tool calls, go to reasoning
            has_tool_messages = any(isinstance(msg, ToolMessage) for msg in messages)
            if has_tool_messages:
                return "reasoning"

            return END

        # Build the state graph
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("reasoning", reasoning_node)

        # Add edges
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent", should_continue, {"tools": "tools", "reasoning": "reasoning", END: END}
        )
        workflow.add_edge("tools", "agent")
        workflow.add_edge("reasoning", END)

        return workflow

    def _generate_tool_reflection(self, tool_name: str, tool_args: dict) -> str:
        """Fallback to generate a first-person reflection about what the agent is doing."""
        operation = _extract_operation_from_tool_name(tool_name)
        display_name = operation.replace("_", " ")
        return f"I'm running {display_name}..."

    def _generate_completion_reflection(self, tool_name: str, result: dict) -> str:
        """Generate a short, first-person reflection after a tool completes.

        This is intentionally minimal to satisfy unit tests and provide
        user-friendly progress updates.
        """
        # Knowledge search completion should not add extra chatter
        if tool_name == "search_knowledge_base":
            return ""

        # Specialized handling for Redis diagnostics
        if tool_name == "get_detailed_redis_diagnostics":
            status = (result or {}).get("status")
            if status == "success":
                # If memory diagnostics are present, mention memory usage explicitly
                try:
                    mem = (result.get("diagnostics", {}) or {}).get("memory", {})
                    used = mem.get("used_memory_bytes")
                    maxm = mem.get("maxmemory_bytes")
                    if used is not None and maxm is not None:
                        return f"Memory usage: {used} bytes used out of {maxm}. I can recommend actions next."
                except Exception:
                    pass
                return "Diagnostics collected successfully."
            else:
                return (
                    "I wasn't able to collect the diagnostics. Let me try a different approach..."
                )

        # Default generic completion message
        display = (tool_name or "").replace("_", " ").strip()
        return f"I've completed {display}."

    async def process_query(
        self,
        query: str,
        session_id: str,
        user_id: str,
        max_iterations: int = settings.max_iterations,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> str:
        """Process a single SRE query through the LangGraph workflow.

        Args:
            query: User's SRE question or request
            session_id: Session identifier for conversation context
            user_id: User identifier
            max_iterations: Maximum number of workflow iterations
            context: Additional context including instance_id if specified

        Returns:
            Agent's response as a string
        """
        logger.info(f"Processing SRE query for user {user_id}, session {session_id}")

        # Set progress callback for this query
        if progress_callback:
            self.progress_callback = progress_callback

        # Determine target Redis instance from context
        target_instance = None
        enhanced_query = query

        if context and context.get("instance_id"):
            instance_id = context["instance_id"]
            logger.info(f"Processing query with Redis instance context: {instance_id}")

            # Resolve instance ID to get actual connection details
            try:
                instances = await get_instances_from_redis()
                for instance in instances:
                    if instance.id == instance_id:
                        target_instance = instance
                        break

                if target_instance:
                    # Get connection URL and mask credentials for logging
                    conn_url_str = _get_secret_value(target_instance.connection_url)
                    masked_url = _mask_redis_url_credentials(conn_url_str)
                    logger.info(f"Found target instance: {target_instance.name} ({masked_url})")

                    # Add instance context to the query
                    enhanced_query = f"""User Query: {query}

IMPORTANT CONTEXT: This query is specifically about Redis instance:
- Instance ID: {instance_id}
- Instance Name: {target_instance.name}
- Connection URL: {conn_url_str}
- Environment: {target_instance.environment}
- Usage: {target_instance.usage}

Your diagnostic tools are PRE-CONFIGURED for this instance. You do NOT need to specify redis_url or instance details - they are already set. Just call the tools directly.

SAFETY REQUIREMENT: You MUST verify you can connect to and gather data from this specific Redis instance before making any recommendations. If you cannot get basic metrics like maxmemory, connected_clients, or keyspace info, you lack sufficient information to make recommendations.

Please use the available tools to get information about this specific Redis instance and provide targeted troubleshooting and analysis."""
                else:
                    logger.warning(
                        f"Instance {instance_id} not found, proceeding without specific instance context"
                    )
                    enhanced_query = f"""User Query: {query}

CONTEXT: This query mentioned Redis instance ID: {instance_id}, but the instance was not found in the system. Please proceed with general Redis troubleshooting."""
            except Exception as e:
                logger.error(f"Failed to resolve instance {instance_id}: {e}")
                enhanced_query = f"""User Query: {query}

CONTEXT: This query mentioned Redis instance ID: {instance_id}, but there was an error retrieving instance details. Please proceed with general Redis troubleshooting."""

        else:
            # No specific instance provided - check if we should auto-detect
            logger.info("No specific Redis instance provided, checking for available instances")

            # First, check if the user is providing connection details in this message
            instance_details = _extract_instance_details_from_message(query)
            if instance_details:
                logger.info(
                    "Detected connection details in user message, attempting to create instance"
                )
                try:
                    new_instance = await create_instance_programmatically(
                        name=instance_details["name"],
                        connection_url=instance_details["connection_url"],
                        environment=instance_details["environment"],
                        usage=instance_details["usage"],
                        description=instance_details.get(
                            "description", "Created by agent from user-provided details"
                        ),
                        created_by="agent",
                        user_id=user_id,
                    )
                    logger.info(
                        f"Successfully created instance: {new_instance.name} ({new_instance.id})"
                    )

                    # Use the newly created instance
                    target_instance = new_instance
                    redis_url_str = target_instance.connection_url.get_secret_value()
                    host, port = _parse_redis_connection_url(redis_url_str)
                    redis_url = redis_url_str

                    enhanced_query = f"""User Query: {query}

INSTANCE CREATED: I've created a new Redis instance configuration based on the connection details you provided:
- Instance Name: {target_instance.name}
- Instance ID: {target_instance.id}
- Host: {host}
- Port: {port}
- Environment: {target_instance.environment}
- Usage: {target_instance.usage}

When using Redis diagnostic tools, use this Redis URL: {redis_url}

Now I'll analyze this instance to help with your original query. Let me gather some diagnostic information first.

SAFETY REQUIREMENT: You MUST verify you can connect to and gather data from this Redis instance before making any recommendations. If you cannot get basic metrics like maxmemory, connected_clients, or keyspace info, you lack sufficient information to make recommendations."""

                except ValueError as e:
                    logger.warning(f"Failed to create instance from user details: {e}")
                    enhanced_query = f"""User Query: {query}

I detected connection details in your message, but I couldn't create the instance configuration: {str(e)}

Please verify the details and try again, or let me know if you'd like help with general Redis knowledge instead."""

            if not target_instance:
                # No instance created from user input, check existing instances
                try:
                    instances = await get_instances_from_redis()
                    if len(instances) == 1:
                        # Only one instance available - use it automatically
                        target_instance = instances[0]
                        redis_url_str = target_instance.connection_url.get_secret_value()
                        host, port = _parse_redis_connection_url(redis_url_str)
                        redis_url = redis_url_str
                        logger.info(
                            f"Auto-detected single Redis instance: {target_instance.name} ({redis_url})"
                        )

                        enhanced_query = f"""User Query: {query}

AUTO-DETECTED CONTEXT: Since no specific Redis instance was mentioned, I am analyzing the available Redis instance:
- Instance Name: {target_instance.name}
- Host: {host}
- Port: {port}
- Environment: {target_instance.environment}
- Usage: {target_instance.usage}

When using Redis diagnostic tools, use this Redis URL: {redis_url}

SAFETY REQUIREMENT: You MUST verify you can connect to and gather data from this Redis instance before making any recommendations. If you cannot get basic metrics like maxmemory, connected_clients, or keyspace info, you lack sufficient information to make recommendations."""

                    elif len(instances) > 1:
                        # Multiple instances - ask user to specify
                        instance_list = "\n".join(
                            [
                                f"- {inst.name} ({inst.environment}): {inst.connection_url}"
                                for inst in instances
                            ]
                        )
                        enhanced_query = f"""User Query: {query}

MULTIPLE REDIS INSTANCES DETECTED: I found {len(instances)} Redis instances configured. Please specify which instance you want me to analyze:

{instance_list}

To get targeted analysis, please rephrase your query to specify which instance, or use the instance selector in the UI."""

                    else:
                        # No instances configured - try to gather info or route to knowledge agent
                        logger.warning("No Redis instances configured")

                        # Check if this query seems to be about a specific Redis instance
                        # or if it's more general knowledge-seeking
                        from ..agent.router import AgentType, get_agent_router

                        router = get_agent_router()
                        suggested_agent = router.route_query(query, context)

                        if suggested_agent == AgentType.KNOWLEDGE_ONLY:
                            # Route to knowledge agent for general queries
                            logger.info(
                                "No instances configured and query is general - suggesting knowledge agent"
                            )
                            enhanced_query = f"""User Query: {query}

NO REDIS INSTANCES CONFIGURED: I cannot analyze specific Redis instances because none are configured in the system.

However, your query appears to be seeking general Redis knowledge or best practices. I can help you with:
- General Redis concepts and troubleshooting approaches
- SRE best practices for Redis
- Documentation and learning resources
- Troubleshooting methodologies

Would you like me to help with general Redis knowledge, or do you have a specific Redis instance you'd like me to analyze? If you have a specific instance, please provide:
1. Redis connection URL (e.g., redis://hostname:6379)
2. Environment (development, staging, production)
3. Usage type (cache, analytics, session, queue, etc.)

I can then create an instance configuration and help you troubleshoot it."""
                        else:
                            # Query seems Redis-specific - ask for connection details
                            logger.info(
                                "No instances configured but query seems Redis-specific - requesting connection details"
                            )
                            enhanced_query = f"""User Query: {query}

NO REDIS INSTANCES CONFIGURED: I cannot analyze specific Redis instances because none are configured in the system.

Your query appears to be about a specific Redis instance. To help you, I need to create an instance configuration. Please provide:

1. **Redis Connection URL** (required): e.g., redis://hostname:6379 or redis://user:password@hostname:6379
2. **Environment** (required): development, staging, or production
3. **Usage Type** (required): cache, analytics, session, queue, or custom
4. **Description** (optional): Brief description of this Redis instance

Once you provide these details, I'll create an instance configuration and help you troubleshoot it.

Alternatively, if you're looking for general Redis knowledge or best practices (not specific to an instance), let me know and I can help with that instead."""

                except Exception as e:
                    logger.error(f"Failed to check available instances: {e}")

        # Create initial state with conversation history
        # If conversation_history is provided, include it before the new query
        initial_messages = []
        if conversation_history:
            initial_messages = list(conversation_history)
            logger.info(f"Including {len(conversation_history)} messages from conversation history")
            for i, msg in enumerate(conversation_history):
                logger.info(f"  History[{i}]: {type(msg).__name__} - {str(msg.content)[:100]}")
        initial_messages.append(HumanMessage(content=enhanced_query))
        logger.info(f"Total messages in initial_state: {len(initial_messages)}")

        initial_state: AgentState = {
            "messages": initial_messages,
            "session_id": session_id,
            "user_id": user_id,
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": max_iterations,
        }

        # Store instance context in the state for tool execution
        if context and context.get("instance_id"):
            initial_state["instance_context"] = context

        # INSTANCE TYPE TRIAGE: Detect and validate instance type before loading tools
        if target_instance and target_instance.instance_type in ["unknown", None]:
            logger.info(
                f"Instance '{target_instance.name}' has unknown type, attempting LLM-based detection"
            )
            detected_type = await _detect_instance_type_with_llm(target_instance, self.llm)

            if detected_type != "unknown":
                logger.info(
                    f"Detected instance type '{detected_type}' for '{target_instance.name}'"
                )
                # Update the instance with detected type
                target_instance.instance_type = detected_type

                # Save the updated instance type
                try:
                    instances = await get_instances_from_redis()
                    for i, inst in enumerate(instances):
                        if inst.id == target_instance.id:
                            instances[i] = target_instance
                            break
                    await save_instances_to_redis(instances)
                    logger.info(
                        f"Updated instance '{target_instance.name}' with type '{detected_type}'"
                    )
                except Exception as e:
                    logger.error(f"Failed to save updated instance type: {e}")

        # Validate Redis Enterprise instances have required admin credentials
        # Check for None, empty string, or whitespace-only strings
        has_admin_url = (
            target_instance and target_instance.admin_url and target_instance.admin_url.strip()
        )

        if (
            target_instance
            and target_instance.instance_type == "redis_enterprise"
            and not has_admin_url
        ):
            logger.warning(
                f"Redis Enterprise instance '{target_instance.name}' detected but missing admin_url"
            )

            # Return early with helpful message asking for admin credentials
            class AgentResponseStr(str):
                def get(self, key: str, default: Any = None):
                    if key == "content":
                        return str(self)
                    return default

            return AgentResponseStr(
                f"""I've detected that **{target_instance.name}** is a Redis Enterprise instance, but I'm missing the admin API credentials needed for full diagnostics.

To enable Redis Enterprise cluster monitoring and diagnostics, please provide:

1. **Admin API URL** (typically port 9443)
2. **Admin Username** (e.g., `admin@redis.com`)
3. **Admin Password**

**For example, if you're using the agen'ts Docker Compose setup**:
- Admin URL: `https://redis-enterprise:9443`
- Default username: `admin@redis.com`
- Default password: `admin` (check your docker-compose.yml)

You can update the instance configuration through the UI or API, and I'll be able to:
- ✅ Check cluster health and node status
- ✅ Monitor database (BDB) configurations
- ✅ Detect stuck operations or maintenance mode
- ✅ View shard distribution and replication status
- ✅ Access Redis Enterprise-specific metrics

For now, I can still perform basic Redis diagnostics using the database connection URL, but cluster-level insights will be limited."""
            )

        # Validate Redis Cloud instances have required API credentials
        import os

        has_cloud_credentials = os.getenv("TOOLS_REDIS_CLOUD_API_KEY") and os.getenv(
            "TOOLS_REDIS_CLOUD_API_SECRET_KEY"
        )

        if (
            target_instance
            and target_instance.instance_type == "redis_cloud"
            and not has_cloud_credentials
        ):
            logger.warning(
                f"Redis Cloud instance '{target_instance.name}' detected but missing API credentials"
            )

            # Return early with helpful message asking for API credentials
            class AgentResponseStr(str):
                def get(self, key: str, default: Any = None):
                    if key == "content":
                        return str(self)
                    return default

            return AgentResponseStr(
                f"""I've detected that **{target_instance.name}** is a Redis Cloud instance, but I'm missing the Redis Cloud Management API credentials needed for full cloud resource management.

To enable Redis Cloud Management API tools, please set these environment variables:

1. **TOOLS_REDIS_CLOUD_API_KEY** - Your Redis Cloud API key
2. **TOOLS_REDIS_CLOUD_API_SECRET_KEY** - Your Redis Cloud API secret key

**To get your API credentials**:
1. Log in to [Redis Cloud Console](https://app.redislabs.com/)
2. Navigate to **Settings** → **Account** → **API Keys**
3. Click **Generate API Key**
4. Copy the API Key and Secret Key (secret is only shown once!)

Once configured, I'll be able to:
- ✅ List and inspect subscriptions
- ✅ View database configurations and status
- ✅ Monitor account resources
- ✅ Check task status for async operations
- ✅ Manage users and access control
- ✅ View cloud account details

For now, I can still perform basic Redis diagnostics using the database connection URL, but cloud management features will be limited."""
            )

        # Create ToolManager for this query with the target instance
        async with ToolManager(redis_instance=target_instance) as tool_mgr:
            # Get tools and bind to LLM
            tools = tool_mgr.get_tools()
            tool_schemas = [tool.to_openai_schema() for tool in tools]

            logger.info(f"Loaded {len(tools)} tools for this query")
            for tool in tools:
                logger.debug(f"  - {tool.name}")

            # Rebind LLM with tools for this query
            self.llm_with_tools = self.llm.bind_tools(tool_schemas)

            # Rebuild workflow with the tool manager and target instance
            self.workflow = self._build_workflow(tool_mgr, target_instance)

            # Create MemorySaver for this query
            # NOTE: RedisSaver doesn't support async (aget_tuple raises NotImplementedError)
            # Conversation history is managed by our ThreadManager in Redis
            # and passed via initial_state when needed
            checkpointer = MemorySaver()
            self.app = self.workflow.compile(checkpointer=checkpointer)

            # Configure thread for session persistence and set higher recursion limit
            thread_config = {
                "configurable": {"thread_id": session_id},
                "recursion_limit": self.settings.recursion_limit,
            }

            try:
                # Run the workflow with isolated memory
                final_state = await self.app.ainvoke(initial_state, config=thread_config)

                # Extract the final response
                messages = final_state["messages"]
                if messages and isinstance(messages[-1], AIMessage):
                    response_content = messages[-1].content
                    logger.info(
                        f"SRE agent completed processing with {final_state['iteration_count']} iterations"
                    )

                    class AgentResponseStr(str):
                        def get(self, key: str, default: Any = None):
                            if key == "content":
                                return str(self)
                            return default

                    return AgentResponseStr(response_content)
                else:
                    logger.warning("No valid response generated by SRE agent")

                    class AgentResponseStr(str):
                        def get(self, key: str, default: Any = None):
                            if key == "content":
                                return str(self)
                            return default

                    return AgentResponseStr(
                        "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."
                    )

            except Exception as e:
                logger.error(f"Error processing SRE query: {str(e)}")
                logger.error(f"Error type: {type(e)}")
                logger.error(f"Error args: {e.args}")
                import traceback

                logger.error(f"Traceback: {traceback.format_exc()}")

                class AgentResponseStr(str):
                    def get(self, key: str, default: Any = None):
                        if key == "content":
                            return str(self)
                        return default

                error_msg = str(e) if str(e) else f"{type(e).__name__}: {e.args}"
                return AgentResponseStr(
                    f"I encountered an error while processing your request: {error_msg}. Please try again or contact support if the issue persists."
                )

    async def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of conversation messages
        """
        try:
            thread_config = {"configurable": {"thread_id": session_id}}

            # Get the current state for the thread
            current_state = await self.app.aget_state(config=thread_config)

            if current_state and "messages" in current_state.values:
                messages = current_state.values["messages"]

                # Convert messages to serializable format
                history = []
                for msg in messages:
                    if isinstance(msg, HumanMessage):
                        history.append({"role": "user", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        history.append({"role": "assistant", "content": msg.content})
                    elif isinstance(msg, ToolMessage):
                        history.append({"role": "tool", "content": msg.content})

                return history

        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}")

        return []

    async def get_thread_state(self, session_id: str) -> Dict[str, Any]:
        """Return internal thread state compatible with evaluation helper.

        The evaluator expects a dict containing a ``messages`` list with
        LangChain message objects that may include ``tool_calls`` metadata.
        """
        try:
            thread_config = {"configurable": {"thread_id": session_id}}
            current_state = await self.app.aget_state(config=thread_config)
            if current_state and hasattr(current_state, "values"):
                return {"messages": current_state.values.get("messages", [])}
        except Exception as e:
            logger.error(f"Error getting thread state: {e}")
        return {"messages": []}

    def clear_conversation(self, session_id: str) -> bool:
        """Clear conversation history for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            # Note: MemorySaver doesn't have a direct clear method
            # In production, you'd want to use a more sophisticated checkpointer
            # For now, we'll rely on the natural expiration of memory
            logger.info(f"Conversation clear requested for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing conversation: {e}")
            return False

    async def _fact_check_response(
        self, response: str, diagnostic_data: str = None
    ) -> Dict[str, Any]:
        """Fact-check an agent response for technical accuracy and URL validity.

        Args:
            response: The agent's response to fact-check
            diagnostic_data: Optional diagnostic data that informed the response

        Returns:
            Dict containing fact-check results including URL validation
        """
        try:
            # Extract URLs from response for validation
            import re

            url_pattern = r'https?://[^\s<>"{}|\\^`[\]]+[^\s<>"{}|\\^`[\].,;:!?)]'
            urls_in_response = re.findall(url_pattern, response)

            # Validate URLs if any were found
            url_validation_results = []
            if urls_in_response:
                logger.info(f"Found {len(urls_in_response)} URLs to validate: {urls_in_response}")

                # Import validation function from core tasks
                from ..core.tasks import validate_url

                # Validate each URL (with shorter timeout for fact-checking)
                for url in urls_in_response:
                    validation_result = await validate_url(url, timeout=3.0)
                    url_validation_results.append(validation_result)

                    if not validation_result["valid"]:
                        logger.warning(
                            f"Invalid URL detected: {url} - {validation_result['error']}"
                        )

            # Create fact-checker LLM (separate from main agent)
            fact_checker = ChatOpenAI(
                model=self.settings.openai_model,
                openai_api_key=self.settings.openai_api_key,
            )

            # Include URL validation results in the fact-check input
            url_validation_summary = ""
            if url_validation_results:
                invalid_urls = [r for r in url_validation_results if not r["valid"]]
                if invalid_urls:
                    url_validation_summary = f"\n\n## URL Validation Results:\nINVALID URLs found: {[r['url'] for r in invalid_urls]}"
                else:
                    url_validation_summary = f"\n\n## URL Validation Results:\nAll {len(url_validation_results)} URLs are valid and accessible."

            # Detect CLI commands (focus on rladmin) in the response
            cli_detection_summary = ""
            unique_cmds = []
            try:
                cli_matches = re.findall(r"(rladmin\b[^\n]*)", response)
                if cli_matches:
                    for cmd in cli_matches:
                        if cmd not in unique_cmds:
                            unique_cmds.append(cmd)
                    cli_detection_summary = (
                        "\n\n## Detected CLI Commands (to validate)\n- " + "\n- ".join(unique_cmds)
                    )
            except Exception:
                pass

            # Validate detected CLI commands against knowledge base documentation
            cli_docs_validation_summary = ""
            unmatched_commands: list[str] = []
            _doc_search_ran = False
            try:
                if unique_cmds:
                    from redis_sre_agent.core.knowledge_helpers import (
                        search_knowledge_base_helper,
                    )

                    _doc_search_ran = True

                    def _build_query_from_cmd(cmd: str) -> str:
                        # Build a compact query like: "rladmin node maintenance_mode"
                        parts = []
                        for tok in cmd.split():
                            t = tok.strip()
                            if not t:
                                continue
                            # stop at obvious option/value tokens
                            if t.startswith("-") or t.isdigit():
                                break
                            # include rladmin and alpha/underscore tokens
                            if t.lower() == "rladmin" or t.replace("_", "").isalpha():
                                parts.append(t)
                        # Limit length to avoid noisy queries
                        return " ".join(parts[:4])

                    lines = []
                    for cmd in unique_cmds:
                        q = _build_query_from_cmd(cmd)
                        if not q:
                            continue
                        try:
                            res = await search_knowledge_base_helper(query=q, limit=5)
                            count = int(res.get("results_count", 0) or 0)
                            sources = [r.get("source", "") for r in res.get("results", [])]
                            if count == 0:
                                unmatched_commands.append(cmd)
                                lines.append(f"- {cmd}: 0 matching docs found for query '{q}'")
                            else:
                                preview_sources = (
                                    ", ".join(sources[:2]) if sources else "(no sources)"
                                )
                                lines.append(
                                    f"- {cmd}: {count} doc match(es) for query '{q}'; top sources: {preview_sources}"
                                )
                        except Exception as _e:
                            # Continue validating other commands; summarize at end
                            lines.append(
                                f"- {cmd}: error during doc lookup; will defer to LLM fact-check"
                            )
                    if lines:
                        cli_docs_validation_summary = (
                            "\n\n## CLI Documentation Lookup:\n" + "\n".join(lines)
                        )
            except Exception as e:
                logger.info(f"Skipping CLI doc validation during fact-checking: {e}")

            # Prepare fact-check prompt
            fact_check_input = f"""
## Agent Response to Fact-Check:
{response}

## Diagnostic Data (if available):
{diagnostic_data if diagnostic_data else "No diagnostic data provided"}{url_validation_summary}{cli_docs_validation_summary}{cli_detection_summary}

Please review this Redis SRE agent response for factual accuracy, command validity (especially `rladmin`), and URL validity. Include any invalid commands or URLs as errors in your assessment.
"""

            messages = [
                {"role": "system", "content": FACT_CHECKER_PROMPT},
                {"role": "user", "content": fact_check_input},
            ]

            # Retry fact-check with parsing
            async def _fact_check_with_retry():
                """Inner function for fact-check retry logic."""
                fact_check_response = await fact_checker.ainvoke(messages)

                # Handle markdown code blocks if present
                response_text = fact_check_response.content.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]  # Remove ```json
                if response_text.endswith("```"):
                    response_text = response_text[:-3]  # Remove ```
                response_text = response_text.strip()

                # Parse JSON response - this will raise JSONDecodeError if parsing fails
                result = json.loads(response_text)
                return result

            try:
                result = await self._retry_with_backoff(
                    _fact_check_with_retry,
                    max_retries=self.settings.llm_max_retries,
                    initial_delay=self.settings.llm_initial_delay,
                    backoff_factor=self.settings.llm_backoff_factor,
                )
                logger.info(
                    f"Fact-check completed: {'errors found' if result.get('has_errors') else 'no errors'}"
                )
                # Enforce invalid_command when we successfully ran doc validation and found no docs for a detected command
                try:
                    if _doc_search_ran and unmatched_commands:
                        errs = result.get("errors") or []
                        for cmd in unmatched_commands:
                            errs.append(
                                {
                                    "claim": cmd,
                                    "issue": "No matching documentation found for this command syntax; verify against official Redis docs.",
                                    "category": "invalid_command",
                                }
                            )
                        result["errors"] = errs
                        result["has_errors"] = True
                except Exception:
                    # Never break on enforcement
                    pass
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Fact-checker returned invalid JSON after retries: {e}")
                return {
                    "has_errors": False,
                    "validation_notes": f"Fact-checker response parsing failed after {2 + 1} attempts",
                }

        except Exception as e:
            logger.error(f"Error during fact-checking: {e}")
            # Don't block on fact-check failures - return graceful fallback

            return {
                "has_errors": False,
                "validation_notes": f"Fact-checking unavailable ({str(e)[:50]}...)",
                "fact_check_error": True,
            }

    async def process_query_with_fact_check(
        self,
        query: str,
        session_id: str,
        user_id: str,
        max_iterations: int = settings.max_iterations,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> str:
        """Process a query with fact-checking and potential retry.

        Args:
            query: User's SRE question or request
            session_id: Session identifier for conversation context
            user_id: User identifier
            max_iterations: Maximum number of workflow iterations
            context: Additional context including instance_id if specified
            progress_callback: Optional callback for progress updates
            conversation_history: Optional conversation history for context

        Returns:
            Agent's response as a string
        """
        # First attempt - normal processing
        response = await self.process_query(
            query,
            session_id,
            user_id,
            max_iterations,
            context,
            progress_callback,
            conversation_history,
        )

        # Safety evaluation - check for dangerous recommendations
        safety_result = await self._safety_evaluate_response(query, response)

        if not safety_result.get("safe", True):
            logger.warning(f"Safety evaluation failed: {safety_result}")

            risk_level = safety_result.get("risk_level", "medium")
            violations = safety_result.get("violations", [])

            # Only trigger corrections for medium risk and above
            if risk_level in ["medium", "high", "critical"]:
                logger.error(f"SAFETY VIOLATION DETECTED (risk: {risk_level}): {violations}")

                correction_guidance = safety_result.get("corrective_guidance", "")
                safety_result.get("reasoning", "")

                if correction_guidance or violations:
                    try:
                        # Create comprehensive correction query with full safety context
                        safety_json = json.dumps(safety_result, indent=2)

                        correction_query = f"""INTERNAL SAFETY CORRECTION - DO NOT MENTION THIS TO THE USER

The user asked: {query}

A safety evaluator identified problems with your previous response:
{safety_json}

Your task:
1. Generate a NEW, COMPLETE response to the user's original query
2. Address each specific violation listed in the safety evaluation
3. Provide safer alternatives that achieve the same operational goals
4. Include appropriate warnings about any remaining risks
5. Ensure logical consistency between your usage pattern analysis and recommendations

SPECIFIC GUIDANCE:
- If flagged for persistence changes: Suggest gradual migration steps with data backup
- If flagged for eviction policies: Recommend investigation before policy changes
- If flagged for restarts: Include steps to ensure data persistence before restart
- If flagged for contradictions: Align recommendations with your usage pattern analysis

CRITICAL: Your response must be directed at the USER, not at the safety evaluator. Do not say things like "I've addressed the safety concerns" or "as noted in the evaluation". Just provide a safe, helpful response to their original question as if this is your first response."""

                        # Retry the safety correction with backoff
                        async def _safety_correction():
                            return await self.process_query(
                                correction_query,
                                session_id,
                                user_id,
                                max_iterations,
                                context,
                                progress_callback,
                                conversation_history,
                            )

                        corrected_response = await self._retry_with_backoff(
                            _safety_correction,
                            max_retries=self.settings.llm_max_retries,
                            initial_delay=self.settings.llm_initial_delay,
                            backoff_factor=self.settings.llm_backoff_factor,
                        )

                        # Verify the correction is safer
                        safety_recheck = await self._safety_evaluate_response(
                            query, corrected_response, is_correction_recheck=True
                        )
                        if safety_recheck.get("safe", True):
                            logger.info("Response corrected after safety evaluation")
                            return corrected_response
                        else:
                            logger.error(
                                f"Correction still unsafe - recheck violations: {safety_recheck.get('violations', [])}"
                            )
                            logger.error(
                                f"Recheck risk level: {safety_recheck.get('risk_level', 'unknown')}"
                            )
                            # If the correction attempt reduced the risk level, accept it even if not perfect
                            original_risk = safety_result.get("risk_level", "high")
                            recheck_risk = safety_recheck.get("risk_level", "high")
                            risk_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}

                            if risk_levels.get(recheck_risk, 3) <= risk_levels.get(
                                original_risk, 3
                            ):
                                logger.info("Correction reduced risk level - accepting response")
                                return corrected_response
                            else:
                                return "⚠️ SAFETY ALERT: This request requires manual review due to potential data loss risks. Please consult with a Redis expert before proceeding."

                    except Exception as correction_error:
                        logger.error(f"Error during safety correction: {correction_error}")
                        return "⚠️ SAFETY ALERT: This request requires manual review due to potential data loss risks."
            else:
                # Low risk violations - log but don't correct
                logger.info(f"Low-risk safety issues noted (risk: {risk_level}): {violations}")

        # Fact-check the response (if it passed safety evaluation)
        fact_check_result = await self._fact_check_response(response)

        if fact_check_result.get("has_errors") and not fact_check_result.get("fact_check_error"):
            logger.warning("Fact-check identified errors in agent response")

            # Create detailed research query with full fact-check context
            fact_check_details = fact_check_result.get("errors", [])
            research_topics = fact_check_result.get("suggested_research", [])

            if research_topics or fact_check_details:
                # Include the full fact-check JSON for context
                fact_check_json = json.dumps(fact_check_result, indent=2)

                research_query = f"""INTERNAL CORRECTION TASK - DO NOT MENTION THIS TO THE USER

The user asked: {query}

A fact-checker identified these technical errors in your previous response:
{fact_check_json}

Your task:
1. Research the identified topics using search_knowledge_base tool
2. Generate a NEW, COMPLETE response to the user's original query
3. Incorporate the corrections silently - DO NOT apologize or mention the fact-checker
4. Address the user directly as if this is your first response
5. Ensure all Redis concepts, metrics, and recommendations are technically accurate

IMPORTANT: Your response must be directed at the USER, not at the fact-checker. Do not say things like "I've corrected the errors" or "as you pointed out". Just provide a corrected, helpful response to their original question."""

                logger.info("Initiating corrective research query with full fact-check context")
                try:
                    # Process the corrective query with retry logic
                    async def _fact_check_correction():
                        return await self.process_query(
                            research_query, session_id, user_id, max_iterations, context=context
                        )

                    corrected_response = await self._retry_with_backoff(
                        _fact_check_correction,
                        max_retries=self.settings.llm_max_retries,
                        initial_delay=self.settings.llm_initial_delay,
                        backoff_factor=self.settings.llm_backoff_factor,
                    )

                    # Return the corrected response without exposing internal fact-checking
                    return corrected_response
                except Exception as correction_error:
                    logger.error(f"Error during correction attempt: {correction_error}")
                    # Fall back to original response rather than failing
                    return response
        elif fact_check_result.get("fact_check_error"):
            logger.info("Fact-check completed: Using original response (fact-check unavailable)")

        return response

    async def _retry_with_backoff(
        self, func, max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0
    ):
        """
        Retry a function with exponential backoff.

        Args:
            func: Async function to retry
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            backoff_factor: Multiplier for delay between retries

        Returns:
            Function result on success

        Raises:
            Last exception if all retries fail
        """
        delay = initial_delay
        last_exception = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                return await func()
            except Exception as e:
                last_exception = e
                if attempt == max_retries:  # Last attempt failed
                    logger.error(f"All {max_retries + 1} attempts failed. Last error: {str(e)}")
                    raise e

                logger.warning(
                    f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor

        # This should never be reached, but just in case
        raise last_exception

    async def _safety_evaluate_response(
        self, original_query: str, response: str, is_correction_recheck: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluate response for dangerous recommendations that could cause data loss.

        This safety evaluator specifically checks for Redis data persistence safety:
        - Ensures eviction policies aren't suggested for persistent data stores
        - Validates that recommendations align with identified usage patterns
        - Flags logic contradictions between analysis and recommendations

        Args:
            original_query: The original user query (may contain diagnostic data)
            response: The agent's response to evaluate

        Returns:
            Dict containing safety evaluation results
        """
        safety_prompt = """
You are a Redis SRE Safety Evaluator. Your job is to identify recommendations
that could cause SIGNIFICANT data loss or system failure.

EVALUATE THIS RESPONSE FOR SERIOUS SAFETY CONCERNS:

ORIGINAL QUERY:
{original_query}

AGENT RESPONSE:
{response}

Only flag as unsafe if the recommendations could cause:
1. **Immediate data loss** - Destructive eviction policies on persistent stores
2. **Logical contradictions** - Actions that contradict the usage pattern analysis
3. **System failure** - Operations that would crash or corrupt Redis

DO NOT flag as unsafe:
- Recommendations with appropriate warnings about risks
- Suggestions to disable snapshots IF accompanied by proper migration guidance
- Restart recommendations IF they include data safety precautions
- Operations that carry operational risk but are standard Redis practices
- Corrected responses that include safety warnings and alternative approaches

RESPONSE FORMAT:
{{
    "safe": true/false,
    "risk_level": "low|medium|high|critical",
    "violations": ["only SERIOUS concerns that could cause data loss"],
    "corrective_guidance": "specific guidance for safer alternatives",
    "reasoning": "explanation focusing on data protection"
}}

Focus on preventing data loss, not operational inconvenience. Standard Redis
operations with appropriate warnings should be considered safe.

{"CORRECTION RECHECK: This is a safety recheck of a corrected response. Be more lenient - if the response includes appropriate warnings and safer alternatives, consider it safe." if is_correction_recheck else ""}
"""

        async def _evaluate_with_retry():
            """Inner function for retry logic."""
            try:
                # Safely convert objects to strings, handling MagicMock objects
                def safe_str(obj):
                    try:
                        return str(obj)
                    except Exception:
                        return repr(obj)

                query_str = safe_str(original_query)
                response_str = safe_str(response)

                # Use safer string replacement to avoid MagicMock formatting issues
                formatted_prompt = safety_prompt.replace("{original_query}", query_str)
                formatted_prompt = formatted_prompt.replace("{response}", response_str)

                safety_response = await self.llm.ainvoke([SystemMessage(content=formatted_prompt)])
            except Exception as format_error:
                logger.error(f"Error formatting safety prompt: {format_error}")
                raise

            # Parse the JSON response - this will raise JSONDecodeError if parsing fails
            result = json.loads(safety_response.content)
            return result

        try:
            # Use retry logic for both LLM call and JSON parsing
            result = await self._retry_with_backoff(
                _evaluate_with_retry,
                max_retries=self.settings.llm_max_retries,
                initial_delay=self.settings.llm_initial_delay,
                backoff_factor=self.settings.llm_backoff_factor,
            )
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Safety evaluation JSON parsing failed after retries: {str(e)}")
            return {
                "safe": False,
                "violations": [
                    "Could not parse safety evaluation response after multiple attempts"
                ],
                "corrective_guidance": "Manual safety review required due to persistent parsing error",
                "reasoning": f"Safety evaluation response was not in expected JSON format after {self.settings.llm_max_retries + 1} attempts",
            }
        except Exception as e:
            try:
                error_str = str(e)
            except Exception:
                error_str = repr(e)
            logger.error(f"Safety evaluation failed after retries: {error_str}")
            return {
                "safe": False,
                "violations": ["Safety evaluation failed"],
                "risk_level": "high",
                "corrective_guidance": "Manual review required - safety evaluation error",
                "reasoning": f"Safety evaluation error after retries: {str(e)}",
            }


def get_sre_agent() -> SRELangGraphAgent:
    """Create a new SRE agent instance for each task to prevent cross-contamination.

    Previously this was a singleton, but that caused cross-contamination between
    different tasks/threads when multiple tasks ran concurrently. Each task now
    gets its own isolated agent instance.
    """
    return SRELangGraphAgent()
