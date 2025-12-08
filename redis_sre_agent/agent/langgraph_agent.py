"""LangGraph-based SRE Agent implementation.

This module implements a LangGraph workflow for SRE operations, providing
multi-turn conversation handling, tool calling integration, and state management.
"""

import asyncio
import hashlib
import json
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict
from urllib.parse import urlparse
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from opentelemetry import trace
from pydantic import BaseModel, Field

from ..agent.router import AgentType, route_to_appropriate_agent
from ..core.config import settings
from ..core.instances import (
    create_instance,
    get_instance_by_id,
    get_instances,
    save_instances,
)
from ..tools.manager import ToolManager
from .helpers import log_preflight_messages
from .prompts import SRE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _extract_operation_from_tool_name(tool_name: str) -> str:
    """Extract human-readable operation name from full tool name.

    Tool names follow the format: {provider}_{hash}_{operation}
    Example: re_admin_ffffa3_get_cluster_info -> get_cluster_info

    Args:
        tool_name: Full tool name with provider, hash, and operation

    Returns:
        Operation name (e.g., "get_cluster_info")
    """

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
    from pydantic import SecretStr

    if isinstance(secret, SecretStr):
        return secret.get_secret_value()
    return str(secret)


def _mask_redis_url_credentials(url: str) -> str:
    """Mask username and password in Redis URL for safe logging/LLM usage.

    Delegates to core.instances.mask_redis_url to avoid duplication.
    """
    from redis_sre_agent.core.instances import mask_redis_url

    return mask_redis_url(url)


async def _detect_instance_type_with_llm(
    instance: Any,
    llm: Optional[ChatOpenAI] = None,
    memoize: Optional[Callable[[str, Any, List[BaseMessage]], Any]] = None,
) -> str:
    """Use LLM to detect Redis instance type from metadata.

    Analyzes connection URL, description, notes, usage, and other metadata
    to determine if this is redis_enterprise, oss_cluster, oss_single, or redis_cloud.

    Args:
        instance: RedisInstance with metadata to analyze
        llm: Optional LLM to use (creates one if not provided)
        memoize: Optional memoization callback for in-run caching

    Returns:
        Detected instance type: 'redis_enterprise', 'oss_cluster', 'oss_single', 'redis_cloud', or 'unknown'
    """

    # Create LLM if not provided
    if llm is None:
        llm = ChatOpenAI(
            model=settings.openai_model_mini,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout,
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
        if memoize:
            response = await memoize("instance_type", llm, [HumanMessage(content=prompt)])
        else:
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
# Prompts moved to redis_sre_agent/agent/prompts.py

# Fact-checker prompt moved to redis_sre_agent/agent/prompts.py


class AgentState(TypedDict):
    """State schema for the SRE LangGraph agent."""

    messages: List[BaseMessage]
    session_id: str
    user_id: str
    current_tool_calls: List[Dict[str, Any]]
    iteration_count: int
    max_iterations: int
    instance_context: Optional[Dict[str, Any]]  # For Redis instance context
    signals_envelopes: List[Dict[str, Any]]  # Accumulated tool result envelopes across steps


class SREToolCall(BaseModel):
    """Model for SRE tool call requests."""

    tool_name: str = Field(..., description="Name of the SRE tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    tool_call_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique tool call ID"
    )


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
            timeout=self.settings.llm_timeout,
        )

        # Tools will be loaded per-query using ToolManager
        # No tools bound at initialization - they're bound per conversation
        self.llm_with_tools = self.llm  # Will be rebound with tools per query

        # Workflow will be built per-query with the appropriate ToolManager
        # Note: We create a new MemorySaver for each query to ensure proper isolation
        # This prevents cross-contamination between different tasks/threads

        logger.info("SRE LangGraph agent initialized (tools loaded per-query)")

    # ----- In-run memoization helpers -----
    def _begin_run_cache(self) -> None:
        self._run_cache_active = True
        self._llm_cache: Dict[str, Any] = {}

    def _end_run_cache(self) -> None:
        self._run_cache_active = False
        self._llm_cache = {}

    def _messages_cache_key(self, messages: List[BaseMessage]) -> str:
        try:
            serial = []
            for m in messages or []:
                role = m.__class__.__name__
                content = m.content or ""
                if isinstance(content, list):
                    try:
                        c = json.dumps(content, sort_keys=True, default=str)
                    except Exception:
                        c = str(content)
                else:
                    c = str(content)
                serial.append({"role": role, "content": c})
            raw = json.dumps(serial, sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        except Exception:
            # Last resort: non-stable key
            return str(id(messages))

    async def _ainvoke_memo(self, tag: str, llm: Any, messages: List[BaseMessage]):
        if not self._run_cache_active:
            return await llm.ainvoke(messages)
        model = llm.model
        temperature = llm.temperature
        key = f"{tag}|{model}|{temperature}|{self._messages_cache_key(messages)}"
        if key in self._llm_cache:
            return self._llm_cache[key]
        resp = await llm.ainvoke(messages)
        self._llm_cache[key] = resp
        return resp

    def _is_redis_scoped(self, text: str) -> bool:
        """Return True if text clearly concerns Redis/Redis Enterprise/Redis Cloud.
        Conservative: if detection fails, default to True to avoid skipping safety when unsure.
        """
        try:
            import re as _re

            if not text:
                return False
            pattern = r"(\bredis\b|redis[-_ ]enterprise|redis[-_ ]cloud|redis[-_ ]cli|\brladmin\b|\bbdbs?\b|\baof\b|\brdb\b|persistence|eviction|replication|\bcli\b)"
            return _re.search(pattern, str(text), flags=_re.IGNORECASE) is not None
        except Exception:
            return True

    def _should_run_safety_fact(self, text: str) -> bool:
        """Heuristic gate: run corrector only if risky patterns or URLs are present."""
        try:
            import re as _re

            pattern = r"(rladmin|CONFIG\s+SET|FLUSH(?:ALL|DB)|\bEVAL\b|\bKEYS\b|/v\d+/.+(PUT|PATCH|DELETE)|https?://)"
            return _re.search(pattern, str(text or ""), flags=_re.IGNORECASE) is not None
        except Exception:
            return False

    async def _compose_final_markdown(
        self,
        *,
        initial_assessment_lines: List[str],
        per_topic_recommendations: List[Dict[str, Any]],
        instance_ctx: Optional[Dict[str, Any]],
        safety_and_fact_check_notes: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Compose operator-facing Markdown using a small/fast LLM and a strict template.
        Never add new facts; only rephrase & format provided materials.
        """
        payload = {
            "initial_assessment_lines": initial_assessment_lines or [],
            "per_topic_recommendations": per_topic_recommendations or [],
            "instance": instance_ctx or {},
        }
        if safety_and_fact_check_notes:
            payload["safety_and_fact_check_notes"] = safety_and_fact_check_notes

        composer_llm = ChatOpenAI(
            model=self.settings.openai_model_mini,
            openai_api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_timeout,
        )
        from langchain_core.messages import HumanMessage, SystemMessage

        msgs = [
            SystemMessage(
                content="""
You are a careful technical editor. Compose a final operator-facing report in Markdown.
CRITICAL RULES:
- Do NOT invent facts, commands, endpoints, or metrics.
- Use ONLY information present in the provided JSON payload.
- You MAY remove duplicates and merge overlapping content; you MUST NOT add anything new.
- Prefer short, direct sentences. Bold only the most important metrics.
- Code blocks only for commands/API examples that appear in the payload.
- If something is missing, omit it—do not guess.
"""
            ),
            HumanMessage(
                content=(
                    f"""
You will receive a JSON payload with analysis artifacts. It may contain multiple reports or fragments that each follow the same outline.
Produce a SINGLE consolidated Markdown document with ONE set of top-level headings in this exact order (include each heading once):

## Initial Assessment

## What I'm Seeing

## My Recommendation

## Supporting Info

## Safety and Fact Checking (include ONLY if 'safety_and_fact_check_notes' is non-empty)

Consolidation rules (no new facts; deduplication is encouraged):
- Initial Assessment: Synthesize a single brief summary from all
'initial_assessment_lines'. Combine overlapping lines and remove duplicates.
- What I'm Seeing: Aggregate key findings across inputs. Group related items and remove repeated statements/metrics.
- My Recommendation: Use '### <topic or plan title>' sub-headings for each distinct recommendation area across inputs.
  - Merge areas with identical or near-duplicate titles (case/punctuation-insensitive) into one sub-heading.
  - Within each sub-heading, preserve the original step order, remove duplicate
    steps, and collapse identical commands/API examples. Do not invent new steps.
- Supporting Info: Combine and de-duplicate citations/sources.
- Safety and Fact Checking: If provided, summarize 'safety_and_fact_check_notes' as bullet points. Keep it concise and do NOT alter previous sections.
- If a section would be empty, include the heading with a short, neutral sentence — EXCEPT omit the 'Safety and Fact Checking' section entirely when 'safety_and_fact_check_notes' is empty.

Return Markdown only.

JSON payload of analyses artifacts:
```
{json.dumps(payload, default=str)}
```
"""
                )
            ),
        ]
        composed = await self._ainvoke_memo("composer", composer_llm, msgs)
        content = composed.content or ""
        # Normalize to string in case content is a list of parts
        if isinstance(content, list):
            try:
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text") or part.get("content") or ""
                        if isinstance(text, str) and text:
                            parts.append(text)
                    elif isinstance(part, str):
                        parts.append(part)
                content = "\n".join(parts).strip()
            except Exception:
                content = str(content)
        elif not isinstance(content, str):
            content = str(content)

        if not content:
            logger.warning("Final markdown composer returned no content")
            return ""

        # Guardrail: If no safety notes were provided, strip any spurious 'Safety and Fact Checking' section
        if not safety_and_fact_check_notes:
            try:
                import re as _re

                content = _re.sub(
                    r"\n##\s*Safety and Fact Checking[\s\S]*$", "", content, flags=_re.IGNORECASE
                )
            except Exception:
                pass

        return content

    def _build_workflow(
        self, tool_mgr: ToolManager, target_instance: Optional[Any] = None
    ) -> StateGraph:
        """Build the LangGraph workflow for SRE operations.

        Args:
            tool_mgr: ToolManager instance for resolving tool calls
            target_instance: Optional RedisInstance for context-specific prompts
        """
        # Build a quick lookup for ToolDefinition by name for envelopes
        tooldefs_by_name = {t.name: t for t in tool_mgr.get_tools()}

        # Lightweight OTel wrapper to trace per-node execution
        def _trace_node(node_name: str):
            def _decorator(fn):
                async def _wrapped(state: AgentState) -> AgentState:
                    with tracer.start_as_current_span(
                        "langgraph.node",
                        attributes={
                            "langgraph.graph": "sre_agent",
                            "langgraph.node": node_name,
                        },
                    ):
                        return await fn(state)

                return _wrapped

            return _decorator

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

                system_message = SystemMessage(content=system_prompt)
                messages = [system_message] + messages

            # Generate response with tool calling capability using retry logic
            # Sanitize message order for OpenAI: drop orphan tool messages and ensure no tool-first
            def _sanitize_messages_for_llm(msgs: list[BaseMessage]) -> list[BaseMessage]:
                if not msgs:
                    return msgs
                seen_tool_ids = set()
                clean: list[BaseMessage] = []
                for m in msgs:
                    if isinstance(m, AIMessage):
                        try:
                            for tc in m.tool_calls or []:
                                if isinstance(tc, dict):
                                    tid = tc.get("id") or tc.get("tool_call_id")
                                    if tid:
                                        seen_tool_ids.add(tid)
                        except Exception:
                            pass
                        clean.append(m)
                    elif isinstance(m, ToolMessage) or m.type == "tool":
                        tid = m.tool_call_id
                        if tid and tid in seen_tool_ids:
                            clean.append(m)
                        else:
                            # Drop orphan tool message with no preceding assistant tool_calls
                            continue
                    else:
                        clean.append(m)
                # Ensure the first message is not a tool message
                while clean and (isinstance(clean[0], ToolMessage) or clean[0].type == "tool"):
                    clean = clean[1:]
                # If the last message is an assistant with unfulfilled tool_calls, drop it to avoid API 400
                if clean and isinstance(clean[-1], AIMessage) and (clean[-1].tool_calls or []):
                    clean = clean[:-1]
                # Fallback guard: never return an empty list; keep first non-tool from original msgs
                if not clean:
                    for m in msgs:
                        if not (isinstance(m, ToolMessage) or m.type == "tool"):
                            clean = [m]
                            break
                return clean

            messages = _sanitize_messages_for_llm(messages)

            async def _agent_llm_call():
                """Inner function for agent LLM call with retry logic."""
                log_preflight_messages(messages, label="Preflight LLM", logger=logger)
                return await self._ainvoke_memo("agent", self.llm_with_tools, messages)

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

            # Normalize response to a LangChain Message to ensure checkpoint serialization
            if not isinstance(response, BaseMessage):
                content = response.content
                tool_calls = response.tool_calls
                response = AIMessage(
                    content=str(content) if content is not None else "", tool_calls=tool_calls
                )

            # Update state
            new_messages = messages + [response]
            state["messages"] = new_messages
            state["iteration_count"] = iteration_count + 1

            # Track tool calls if any
            if response.tool_calls:
                import json

                norm_calls = []
                for tc in response.tool_calls:
                    name = tc.get("name", "")
                    if not name and isinstance(tc.get("function"), dict):
                        name = tc["function"].get("name", "")
                    args = tc.get("args")
                    if args is None and isinstance(tc.get("function"), dict):
                        arguments = tc["function"].get("arguments")
                        if isinstance(arguments, str):
                            try:
                                args = json.loads(arguments or "{}")
                            except Exception:
                                args = {}
                        elif isinstance(arguments, dict):
                            args = arguments
                    if not isinstance(args, dict):
                        args = {}
                    norm_calls.append(
                        {
                            "tool_call_id": tc.get("id", str(uuid4())),
                            "name": name,
                            "args": args,
                        }
                    )
                state["current_tool_calls"] = norm_calls
                logger.info(f"Agent requested {len(response.tool_calls)} tool calls")
            else:
                state["current_tool_calls"] = []

            return state

        async def tool_node(state: AgentState) -> AgentState:
            """Execute SRE tools via LangGraph's ToolNode while preserving our telemetry.

            - Emit our progress callback before execution
            - Execute tools with ToolNode (handles batching/arg normalization)
            - Pair returned ToolMessages to pending calls to build envelopes and sources
            """
            messages = state["messages"]
            tool_calls = state.get("current_tool_calls", []) or []

            if not tool_calls:
                return state

            # 1) Emit progress updates for each pending tool call
            for tc in tool_calls:
                try:
                    tool_name = tc.get("name")
                    tool_args = tc.get("args") or {}
                    if self.progress_callback and tool_name:
                        status_msg = tool_mgr.get_status_update(
                            tool_name, tool_args
                        ) or self._generate_tool_reflection(tool_name, tool_args)
                        if status_msg:
                            await self.progress_callback(status_msg, "agent_reflection")
                except Exception:
                    pass

            # 2) Build StructuredTool adapters once (resolve via ToolManager)
            try:
                from langgraph.prebuilt import ToolNode as LGToolNode

                from .helpers import build_adapters_for_tooldefs as _build_adapters

                # Centralized adapter builder (returns StructuredTool adapters)
                adapters = await _build_adapters(tool_mgr, list(tooldefs_by_name.values()))

                lg_tool_node = LGToolNode(adapters)

                # 3) Execute with ToolNode
                log_preflight_messages(messages, label="Preflight toolnode-before", logger=logger)
                out = await lg_tool_node.ainvoke({"messages": messages})
                out_messages = out.get("messages", [])
                # Some versions may return only ToolMessages; append deltas to preserve history
                new_tool_messages = [m for m in out_messages if isinstance(m, ToolMessage)]
                logger.info(
                    f"ToolNode returned {len(out_messages)} msgs; appending {len(new_tool_messages)} tool msgs"
                )
                new_messages = messages + new_tool_messages if new_tool_messages else messages

                # 4) Build envelopes by pairing pending calls with returned ToolMessages
                try:
                    from .helpers import build_result_envelope  # local import to avoid cycles

                    new_tool_messages = [
                        m for m in new_messages[len(messages) :] if isinstance(m, ToolMessage)
                    ]
                    for idx, tc in enumerate(tool_calls):
                        tool_name = tc.get("name")
                        tool_args = tc.get("args") or {}
                        tm = new_tool_messages[idx] if idx < len(new_tool_messages) else None
                        env_dict = build_result_envelope(
                            tool_name or f"tool_{idx + 1}", tool_args, tm, tooldefs_by_name
                        )
                        env_list = state.get("signals_envelopes") or []
                        env_list.append(env_dict)
                        state["signals_envelopes"] = env_list
                        data_obj = env_dict.get("data")

                        logger.info(
                            f"tool_node: Envelope built for tool call {tool_name} with args {tool_args}"
                        )
                        logger.info(f"tool_node: Env list now has {len(env_list)} items")

                        # Knowledge fragments progress (best-effort)
                        try:
                            if (
                                self.progress_callback
                                and isinstance(data_obj, dict)
                                and isinstance(tool_name, str)
                                and tool_name.startswith("knowledge_")
                                and tool_name.endswith("_search")
                            ):
                                items = data_obj.get("results") or []
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
                                    except Exception as e:
                                        logger.error(
                                            f"Failed to build fragment from knowledge search result: {e}"
                                        )
                                if fragments:
                                    await self.progress_callback(
                                        "Retrieved knowledge fragments",
                                        "knowledge_sources",
                                        {"fragments": fragments},
                                    )
                        except Exception as e:
                            logger.error(f"Failed to emit knowledge_sources progress update: {e}")
                except Exception as e:
                    # Do not fail the step if envelope recording has issues
                    logger.error(f"Failed to build envelopes: {e}")

                state["messages"] = new_messages
                state["current_tool_calls"] = []
                return state

            except Exception as e:
                logger.exception(f"ToolNode execution failed, falling back to manual loop: {e}")
                # Fallback: no-op; leave state unchanged so the graph can proceed or retry
                return state

        async def reasoning_node(state: AgentState) -> AgentState:
            """Final reasoning node: extract topics, fork per-topic recommendations, then compose.

            This uses a topics-based map/reduce workflow:
            - Parse tool outputs into structured signals (envelopes)
            - Extract distinct topics via structured LLM output
            - Fork N concurrent per-topic recommendation workers
            - Compose a coherent, ordered execution plan and produce the final message
            """
            messages = state["messages"]

            # 1) Extract structured tool results from ToolMessage content
            def _parse_tool_json_blocks(tool_msg_text: str) -> Optional[dict]:
                try:
                    # Heuristic: after "Result:" find first JSON object
                    idx = tool_msg_text.find("Result:")
                    if idx == -1:
                        idx = tool_msg_text.find("Result\n")
                    payload = tool_msg_text[idx + 7 :] if idx != -1 else tool_msg_text
                    # Find first '{'
                    j = payload.find("{")
                    if j == -1:
                        return None
                    candidate = payload[j:]
                    # Try to load as JSON directly
                    return json.loads(candidate)
                except Exception:
                    return None

            # New path: topic extraction with structured output based on full envelopes
            envelopes = state.get("signals_envelopes") or []
            logger.info(f"Reasoning: envelopes captured={len(envelopes)}")
            topics: List[Dict[str, Any]] = []
            try:
                from .models import TopicsList

                extractor_llm = self.llm.with_structured_output(TopicsList)  # return TopicsList
                instance_ctx = {
                    "instance_type": target_instance.instance_type,
                    "name": target_instance.name,
                }
                preface = (
                    "About this JSON: signals from upstream tool calls (each has a tool description, args, and raw JSON results).\n"
                    "Use only these as evidence. Return a list of topics with evidence_keys referencing tool_key.\n"
                    "For EACH topic, include: id, title, category, scope, narrative, evidence_keys, and severity.\n"
                    "severity MUST be one of: critical | high | medium | low, based on operational risk/impact/urgency.\n"
                    "Order the topics by severity (critical->low)."
                )
                payload = json.dumps(envelopes, default=str)
                human = HumanMessage(
                    content=(
                        preface
                        + "\nInstance (JSON):\n"
                        + json.dumps(instance_ctx, default=str)
                        + "\nSignals (JSON):\n"
                        + payload
                    )
                )
                resp = await self._ainvoke_memo(
                    "topics_extractor", extractor_llm, [human]
                )  # TopicsList or similar
                # Normalize to plain dicts list
                items = resp.items if resp else resp
                if isinstance(items, list):
                    topics = [t if isinstance(t, dict) else t.model_dump() for t in items]
                else:
                    topics = []
                logger.info(f"Reasoning: topics extracted={len(topics)}")
                # Order by severity (critical > high > medium > low) and cap to settings
                _sev_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}

                def _sev_score(t: dict) -> int:
                    s = (t.get("severity") or "medium") if isinstance(t, dict) else "medium"
                    s = s.lower() if isinstance(s, str) else "medium"
                    return _sev_order.get(s, 1)

                topics.sort(key=_sev_score, reverse=True)
                max_topics = int(self.settings.max_recommendation_topics or 3)
                if len(topics) > max_topics:
                    topics = topics[:max_topics]
                logger.info(
                    f"Reasoning: topics after severity ordering and cap={len(topics)} (max={max_topics})"
                )

            except Exception as e:
                logger.error(f"Topic extraction failed: {e}")
                topics = []

            # If we have extracted topics, run dynamic per-topic recommendation workers
            if topics:
                from .subgraphs.recommendation_worker import build_recommendation_worker

                rec_tasks = []
                instance_ctx = {
                    "instance_type": target_instance.instance_type,
                    "name": target_instance.name,
                }
                # Build knowledge-only adapters locally (mini model)
                from redis_sre_agent.tools.models import ToolCapability as _ToolCap

                from .helpers import build_adapters_for_tooldefs as _build_adapters

                # Use all knowledge tools for the mini knowledge agent; no op-level filtering.
                knowledge_tools = tool_mgr.get_tools_for_capability(_ToolCap.KNOWLEDGE)
                knowledge_adapters = await _build_adapters(tool_mgr, knowledge_tools)
                if knowledge_adapters:
                    knowledge_llm_base = ChatOpenAI(
                        model=self.settings.openai_model_mini,
                        openai_api_key=self.settings.openai_api_key,
                        timeout=self.settings.llm_timeout,
                    )
                    knowledge_llm = knowledge_llm_base.bind_tools(knowledge_adapters)

                if knowledge_adapters:
                    logger.info(
                        f"Reasoning: knowledge adapters available={len(knowledge_adapters)}; topics to run={len(topics)}"
                    )
                    worker = build_recommendation_worker(
                        knowledge_llm,
                        knowledge_adapters,
                        max_tool_steps=self.settings.max_tool_calls_per_stage,
                        memoize=self._ainvoke_memo,
                    )
                    env_by_key = {
                        e.get("tool_key"): e for e in (state.get("signals_envelopes") or [])
                    }
                    for t in topics:
                        ev_keys = [k for k in (t.get("evidence_keys") or []) if isinstance(k, str)]
                        ev = [env_by_key[k] for k in ev_keys if k in env_by_key]
                        inp = {
                            "messages": [
                                SystemMessage(
                                    content="You will research and then synthesize recommendations for the given topic."
                                ),
                                HumanMessage(
                                    content=f"Topic: {json.dumps(t, default=str)}\nInstance: {json.dumps(instance_ctx, default=str)}\nEvidence: {json.dumps(ev, default=str)}"
                                ),
                            ],
                            "budget": int(self.settings.max_tool_calls_per_stage),
                            "topic": t,
                            "evidence": ev,
                            "instance": instance_ctx,
                        }
                        rec_tasks.append(asyncio.create_task(worker.ainvoke(inp)))
                rec_states = await asyncio.gather(*rec_tasks) if rec_tasks else []
                logger.info(f"Reasoning: recommendation workers completed={len(rec_states)}")
                recommendations = []
                for st in rec_states:
                    r = (st or {}).get("result")
                    if r:
                        recommendations.append(r)
                logger.info(f"Reasoning: recommendations aggregated={len(recommendations)}")

                # Compose final output via unified composer helper
                initial_writeup = None
                for m in reversed(messages):
                    if (
                        isinstance(m, AIMessage)
                        and isinstance(m.content, str)
                        and not m.content.startswith("You are")
                    ):
                        initial_writeup = m.content
                        break
                initial_writeup = initial_writeup or ""

                try:
                    instance_ctx_local = {
                        "instance_type": target_instance.instance_type,
                        "name": target_instance.name,
                    }
                    composed_markdown = await self._compose_final_markdown(
                        initial_assessment_lines=[initial_writeup] if initial_writeup else [],
                        per_topic_recommendations=recommendations or [],
                        instance_ctx=instance_ctx_local,
                    )
                    response = AIMessage(
                        content=composed_markdown if composed_markdown else (initial_writeup or "")
                    )
                except Exception as e:
                    logger.error(f"Failed to compose final markdown: {e}")

                    # Minimal deterministic fallback using standard sections
                    blocks = []
                    blocks.append("## Initial Assessment\n" + (initial_writeup or ""))
                    blocks.append("\n## What I'm Seeing\n")
                    rec_lines = ["\n## My Recommendation"]
                    for rec in recommendations or []:
                        title = rec.get("title") or next(
                            (t.get("title") for t in topics if t.get("id") == rec.get("topic_id")),
                            "Recommendation",
                        )
                        rec_lines.append(f"### {title}")
                        for step in rec.get("steps") or []:
                            desc = step.get("description") or ""
                            if desc:
                                rec_lines.append(f"- {desc}")
                            for cmd in step.get("commands") or []:
                                rec_lines.append(f"```bash\n{cmd}\n```")
                            for api in step.get("api_examples") or []:
                                rec_lines.append(f"```bash\n{api}\n```")
                    blocks.append("\n".join(rec_lines))
                    blocks.append("\n## Supporting Info\n- Plans derived from tool results.")
                    response = AIMessage(content="\n\n".join([b for b in blocks if b]))

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
            if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
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

        # Add nodes (wrapped with per-node tracing spans)
        workflow.add_node("agent", _trace_node("agent")(agent_node))
        workflow.add_node("tools", _trace_node("tools")(tool_node))
        workflow.add_node("reasoning", _trace_node("reasoning")(reasoning_node))

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

    async def _process_query(
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
                target_instance = await get_instance_by_id(instance_id)
                if target_instance:
                    # Get connection URL and mask credentials for logging
                    logger.info(
                        f"Found target instance: {target_instance.name} ({target_instance.connection_url})"
                    )
                    # Add instance context to the query
                    enhanced_query = f"""User Query: {query}

IMPORTANT CONTEXT: This query is specifically about Redis instance:
- Instance ID: {instance_id}
- Instance Name: {target_instance.name}
- Connection URL: {target_instance.connection_url}
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
                    new_instance = await create_instance(
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
                    instances = await get_instances()
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
                        suggested_agent = await route_to_appropriate_agent(query, context)

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
            "signals_envelopes": [],
        }

        # Store instance context in the state for tool execution
        if context and context.get("instance_id"):
            initial_state["instance_context"] = context

        # INSTANCE TYPE TRIAGE: Detect and validate instance type before loading tools
        if target_instance and target_instance.instance_type in ["unknown", None]:
            logger.info(
                f"Instance '{target_instance.name}' has unknown type, attempting LLM-based detection"
            )
            detected_type = await _detect_instance_type_with_llm(
                target_instance, self.llm, memoize=self._ainvoke_memo
            )

            if detected_type != "unknown":
                logger.info(
                    f"Detected instance type '{detected_type}' for '{target_instance.name}'"
                )
                # Update the instance with detected type
                target_instance.instance_type = detected_type

                # Save the updated instance type
                try:
                    instances = await get_instances()
                    for i, inst in enumerate(instances):
                        if inst.id == target_instance.id:
                            instances[i] = target_instance
                            break
                    await save_instances(instances)
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
            # Get tools and bind to LLM via StructuredTool adapters
            tools = tool_mgr.get_tools()

            logger.info(f"Loaded {len(tools)} tools for this query")
            for tool in tools:
                logger.debug(f"  - {tool.name}")

            from .helpers import build_adapters_for_tooldefs as _build_adapters

            adapters = await _build_adapters(tool_mgr, tools)

            # Rebind LLM with tools for this query
            self.llm_with_tools = self.llm.bind_tools(adapters)

            # Rebuild workflow with the tool manager and target instance
            self.workflow = self._build_workflow(tool_mgr, target_instance)

            # Create MemorySaver for this query
            # TODO: Had some trouble with the redis saver
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
                    return response_content
                else:
                    logger.warning("No valid response generated by SRE agent")
                    return "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."

            except Exception as e:
                logger.error(f"Error processing SRE query: {str(e)}")
                logger.error(f"Error type: {type(e)}")
                logger.error(f"Error args: {e.args}")
                import traceback

                logger.error(f"Traceback: {traceback.format_exc()}")

                error_msg = str(e) if str(e) else f"{type(e).__name__}: {e.args}"
                return f"I encountered an error while processing your request: {error_msg}. Please try again."

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
            if current_state and current_state.values:
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
        """Process a query once, then attach Safety and Fact-Checking notes."""
        # Initialize in-run caches (LLM memo; tool cache is per-ToolManager context)
        self._begin_run_cache()
        try:
            # Produce the primary response
            response = await self._process_query(
                query,
                session_id,
                user_id,
                max_iterations,
                context,
                progress_callback,
                conversation_history,
            )

            # Skip correction if out of Redis scope
            try:
                if not (self._is_redis_scoped(query) or self._is_redis_scoped(response)):
                    logger.info("Skipping safety/fact-corrector (out of Redis scope)")
                    return response
            except Exception:
                pass

            # Heuristic gate: only run when risky patterns/URLs present
            if not (self._should_run_safety_fact(response) or self._should_run_safety_fact(query)):
                return response

            # Build a small, bounded corrector with knowledge + utilities tools only
            from langchain_openai import ChatOpenAI

            from .subgraphs.safety_fact_corrector import build_safety_fact_corrector

            # Use always-on providers (knowledge, utilities)
            async with ToolManager(redis_instance=None) as corrector_tool_manager:
                # Select knowledge and utility tools via capabilities.
                from redis_sre_agent.tools.models import ToolCapability as _ToolCap

                # Use all knowledge and utility tools for the corrector; no op-level filtering.
                knowledge_defs = corrector_tool_manager.get_tools_for_capability(_ToolCap.KNOWLEDGE)
                utilities_defs = corrector_tool_manager.get_tools_for_capability(_ToolCap.UTILITIES)
                tooldefs = list(knowledge_defs) + list(utilities_defs)

                # Build StructuredTool adapters centrally
                from .helpers import build_adapters_for_tooldefs as _build_adapters

                adapters = await _build_adapters(corrector_tool_manager, tooldefs)

                # LLM with tools bound via adapters
                corrector_llm_base = ChatOpenAI(
                    model=self.settings.openai_model_mini,
                    openai_api_key=self.settings.openai_api_key,
                    timeout=self.settings.llm_timeout,
                )
                corrector_llm = corrector_llm_base.bind_tools(adapters)

                # Build the compiled subgraph
                corrector = build_safety_fact_corrector(
                    corrector_llm,
                    adapters,
                    max_tool_steps=min(2, int(self.settings.max_tool_calls_per_stage or 2)),
                    memoize=self._ainvoke_memo,
                )

                # Seed with an instruction-only system prompt so the model knows to use tools, then synthesize
                sys = SystemMessage(
                    content=(
                        "You will minimally correct the provided response for safety and factual issues.\n"
                        "- You may call knowledge_* search and utilities (http_head, calculator, date/time) at most 2 times in total.\n"
                        "- Validate up to 5 URLs on well-known docs domains (redis.io, docs.redis.com, redis.com, redis.cloud, github.com) using http_head.\n"
                        "- Do not invent commands. If uncertain, prefer removing or adding a one-line caution.\n"
                        "Stop tool use when sufficient to make minimal edits; synthesis will follow."
                    )
                )
                human = HumanMessage(
                    content=(
                        "Response text to review follows; do not rewrite wholesale — only fix unsafe/incorrect parts."
                    )
                )

                instance_ctx = {}
                try:
                    # Prefer explicit instance facts from context
                    ctx = context or {}
                    instance_ctx = ctx.get("instance") or {}
                    if not instance_ctx:
                        # Fallback: resolve by instance_id and include safe fields only
                        inst_id = ctx.get("instance_id")
                        if inst_id:
                            inst = await get_instance_by_id(inst_id)
                            if inst:
                                # Normalize instance_type to a simple string value when possible
                                _itype = inst.instance_type
                                try:
                                    _itype_val = _itype.value  # Enum-like
                                except Exception:
                                    _itype_val = str(_itype) if _itype is not None else None

                                instance_ctx = {
                                    "id": inst.id,
                                    "name": inst.name,
                                    "environment": inst.environment,
                                    "instance_type": _itype_val,
                                    "status": inst.status,
                                    "version": inst.version,
                                    "memory": inst.memory,
                                    "connections": inst.connections,
                                }
                except Exception:
                    instance_ctx = {}

                initial_state = {
                    "messages": [sys, human],
                    "budget": min(2, int(self.settings.max_tool_calls_per_stage or 2)),
                    "response_text": response,
                    "instance": instance_ctx,
                }

                corr_state = await corrector.ainvoke(initial_state)
                result = (corr_state or {}).get("result") or {}
                edited = str(result.get("edited_response") or "")
                # Replace the original response with the corrected text; do not append audit notes by default
                if edited.strip() and edited.strip() != str(response).strip():
                    # Sanitize any accidental prompt echo sections
                    try:
                        import re as _re

                        edited_sanitized = _re.sub(
                            r"\n+Instance facts \(JSON\):[\s\S]*$", "", edited, flags=_re.IGNORECASE
                        )
                        edited_sanitized = _re.sub(
                            r"\n+Original response to correct \(verbatim\):[\s\S]*$",
                            "",
                            edited_sanitized,
                            flags=_re.IGNORECASE,
                        )
                    except Exception:
                        edited_sanitized = edited
                    return edited_sanitized
                # If no change, just return original
                return response
        finally:
            # Clear LLM memo cache for this run
            try:
                self._end_run_cache()
            except Exception:
                pass

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
                # Enrich logging with OpenAI/HTTP error details when available
                try:
                    status = None
                    body = None
                    try:
                        status = e.status_code  # type: ignore[attr-defined]
                    except AttributeError:
                        try:
                            resp = e.response  # type: ignore[attr-defined]
                            if resp:
                                status = resp.status_code
                        except AttributeError:
                            pass
                    try:
                        raw_body = e.body  # type: ignore[attr-defined]
                        if isinstance(raw_body, (str, bytes)):
                            body = (
                                raw_body.decode("utf-8", errors="ignore")
                                if isinstance(raw_body, (bytes, bytearray))
                                else raw_body
                            )
                    except AttributeError:
                        try:
                            resp = e.response  # type: ignore[attr-defined]
                            if resp is not None:
                                try:
                                    body = resp.text
                                except AttributeError:
                                    try:
                                        body = resp.content
                                    except AttributeError:
                                        pass
                                if isinstance(body, (bytes, bytearray)):
                                    body = body.decode("utf-8", errors="ignore")
                        except AttributeError:
                            pass
                    if status or body:
                        snippet = (body or "")[:2000]
                        logger.error(
                            f"LLM call error details: status={status} body_snippet={snippet}"
                        )
                except Exception:
                    # Never fail due to logging
                    pass

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


def get_sre_agent(*args, **kwargs) -> SRELangGraphAgent:
    """Create a new SRE agent instance for each task to prevent cross-contamination.

    Previously this was a singleton, but that caused cross-contamination between
    different tasks/threads when multiple tasks ran concurrently. Each task now
    gets its own isolated agent instance.
    """
    return SRELangGraphAgent(*args, **kwargs)
