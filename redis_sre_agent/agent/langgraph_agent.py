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
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, Field, create_model

from ..api.instances import (
    create_instance_programmatically,
    get_instances_from_redis,
    save_instances_to_redis,
)
from ..core.config import settings
from ..tools.manager import ToolManager
from .prompts import FACT_CHECKER_PROMPT, SRE_SYSTEM_PROMPT

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


def _preflight_log(msgs: list[BaseMessage], note: str = "") -> None:
    """
    Debug helper: log roles and tool_call_ids before ainvoke
    """
    try:
        from .helpers import log_preflight_messages as _log_preflight

        _log_preflight(msgs, label="Preflight LLM", note=note, logger=logger)
    except Exception as e:
        # Never break flow due to logging
        logger.debug(f"Preflight logging failed: {e}")


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
                content = getattr(m, "content", "")
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
        if not getattr(self, "_run_cache_active", False):
            return await llm.ainvoke(messages)
        model = getattr(llm, "model", None)
        temperature = getattr(llm, "temperature", None)
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

    async def _render_safety_and_fact_check_section(
        self,
        *,
        safety_result: Optional[Dict[str, Any]],
        fact_check_result: Optional[Dict[str, Any]],
    ) -> str:
        """Summarize safety and fact-check outputs into a natural-language section.

        Returns a Markdown string beginning with '## Safety and Fact Checking'.
        """
        # If both are missing, don't render anything
        if not (safety_result or fact_check_result):
            return ""

        payload = {
            "safety": safety_result or {},
            "fact_check": fact_check_result or {},
        }
        summarizer = ChatOpenAI(
            model=self.settings.openai_model_mini,
            openai_api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_timeout,
        )
        sys = SystemMessage(
            content=(
                "You write concise, operator-facing notes. Use plain, direct language.\n"
                "Summarize the provided JSON findings without inventing facts."
            )
        )
        human = HumanMessage(
            content=(
                f"""
Given this JSON with safety and fact-check outputs, write a compact Markdown section:

- Title: ## Safety and Fact Checking
- Subsections: ### Safety, ### Fact Check (include each once)
- Use natural language sentences; bullets are OK but keep them terse and useful.
- If a category is empty/unavailable, say so in one short line.
- Do NOT modify prior recommendations; this section is purely advisory.

JSON:
```
{json.dumps(payload, default=str)}
```
"""
            )
        )
        resp = await self._ainvoke_memo("safety_fact_section", summarizer, [sys, human])
        text = getattr(resp, "content", "")
        return str(text or "")

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
        content = getattr(composed, "content", "")
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
        return content or ""

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
                            for tc in getattr(m, "tool_calls", []) or []:
                                if isinstance(tc, dict):
                                    tid = tc.get("id") or tc.get("tool_call_id")
                                    if tid:
                                        seen_tool_ids.add(tid)
                        except Exception:
                            pass
                        clean.append(m)
                    elif isinstance(m, ToolMessage) or getattr(m, "type", "") == "tool":
                        tid = getattr(m, "tool_call_id", None)
                        if tid and tid in seen_tool_ids:
                            clean.append(m)
                        else:
                            # Drop orphan tool message with no preceding assistant tool_calls
                            continue
                    else:
                        clean.append(m)
                # Ensure the first message is not a tool message
                while clean and (
                    isinstance(clean[0], ToolMessage) or getattr(clean[0], "type", "") == "tool"
                ):
                    clean = clean[1:]
                # If the last message is an assistant with unfulfilled tool_calls, drop it to avoid API 400
                if (
                    clean
                    and isinstance(clean[-1], AIMessage)
                    and (getattr(clean[-1], "tool_calls", None) or [])
                ):
                    clean = clean[:-1]
                # Fallback guard: never return an empty list; keep first non-tool from original msgs
                if not clean:
                    for m in msgs:
                        if not (isinstance(m, ToolMessage) or getattr(m, "type", "") == "tool"):
                            clean = [m]
                            break
                return clean

            messages = _sanitize_messages_for_llm(messages)

            async def _agent_llm_call():
                """Inner function for agent LLM call with retry logic."""
                _preflight_log(messages, "main-agent-before")
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
                content = getattr(response, "content", None)
                tool_calls = getattr(response, "tool_calls", None)
                response = AIMessage(
                    content=str(content) if content is not None else "", tool_calls=tool_calls
                )

            # Update state
            new_messages = messages + [response]
            state["messages"] = new_messages
            state["iteration_count"] = iteration_count + 1

            # Track tool calls if any
            if hasattr(response, "tool_calls") and response.tool_calls:
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

                def _args_model_from_parameters(tool_name: str, params: dict) -> type[BaseModel]:
                    props = (params or {}).get("properties", {}) or {}
                    required = set((params or {}).get("required", []) or [])
                    fields = {}
                    for k, spec in props.items():
                        default = ... if k in required else None
                        fields[k] = (
                            Any,
                            Field(default, description=(spec or {}).get("description")),
                        )
                    # Log schema shape once for debugging
                    logger.debug(
                        f"Tool args schema for {tool_name}: required={list(required)} props={list(props.keys())}"
                    )
                    # Build v2 model and allow extra keys
                    ArgsModel = create_model(f"{tool_name}_Args", __base__=BaseModel, **fields)  # noqa: N806
                    ArgsModel.model_config = ConfigDict(extra="allow")  # type: ignore[attr-defined]
                    return ArgsModel

                adapters = []
                for name, tdef in tooldefs_by_name.items():

                    async def _exec_fn(_name=name, **kwargs):
                        return await tool_mgr.resolve_tool_call(_name, kwargs or {})

                    ArgsModel = _args_model_from_parameters(  # noqa: N806
                        name, getattr(tdef, "parameters", {}) or {}
                    )
                    adapters.append(
                        StructuredTool.from_function(
                            coroutine=_exec_fn,
                            name=name,
                            description=getattr(tdef, "description", "") or "",
                            args_schema=ArgsModel,
                        )
                    )

                lg_tool_node = LGToolNode(adapters)

                # 3) Execute with ToolNode
                _preflight_log(messages, "toolnode-before")
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
                        logger.info(f"tool_node: Env list is now: {env_list}")

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
                    "instance_type": getattr(target_instance, "instance_type", None),
                    "name": getattr(target_instance, "name", None),
                }
                preface = (
                    "About this JSON: signals from upstream tool calls (each has a tool description, args, and raw JSON results).\n"
                    "Use only these as evidence. Return a list of topics with evidence_keys referencing tool_key."
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
                items = getattr(resp, "items", resp)
                if isinstance(items, list):
                    topics = [t if isinstance(t, dict) else t.model_dump() for t in items]
                else:
                    topics = []
                logger.info(f"Reasoning: topics extracted={len(topics)}")
            except Exception as e:
                logger.error(f"Topic extraction failed: {e}")
                topics = []

            # If we have extracted topics, run dynamic per-topic recommendation workers
            if topics:
                from .subgraphs.recommendation_worker import build_recommendation_worker

                rec_tasks = []
                instance_ctx = {
                    "instance_type": getattr(target_instance, "instance_type", None),
                    "name": getattr(target_instance, "name", None),
                }
                # Build knowledge-only adapters locally (mini model)
                all_tools = tool_mgr.get_tools()
                knowledge_tools = [
                    t
                    for t in all_tools
                    if isinstance(t.name, str)
                    and t.name.startswith("knowledge_")
                    and ("search" in t.name or t.name.endswith("_search"))
                ]
                knowledge_tool_schemas = [t.to_openai_schema() for t in knowledge_tools]
                knowledge_adapters = []
                if knowledge_tools:
                    knowledge_llm_base = ChatOpenAI(
                        model=self.settings.openai_model_mini,
                        openai_api_key=self.settings.openai_api_key,
                        timeout=self.settings.llm_timeout,
                    )
                    knowledge_llm = knowledge_llm_base.bind_tools(knowledge_tool_schemas)

                    def _args_model_from_parameters(
                        tool_name: str, params: dict
                    ) -> type[BaseModel]:
                        props = (params or {}).get("properties", {}) or {}
                        required = set((params or {}).get("required", []) or [])
                        fields = {}
                        for k, spec in props.items():
                            default = ... if k in required else None
                            fields[k] = (
                                Any,
                                Field(default, description=(spec or {}).get("description")),
                            )
                        ArgsModel = create_model(f"{tool_name}_Args", __base__=BaseModel, **fields)  # noqa: N806
                        ArgsModel.model_config = ConfigDict(extra="allow")  # type: ignore[attr-defined]
                        return ArgsModel

                    def _mk_adapter(tdef, _StructuredTool=StructuredTool):  # noqa: N803
                        async def _exec(**kwargs):
                            return await tool_mgr.resolve_tool_call(tdef.name, kwargs or {})

                        ArgsModel = _args_model_from_parameters(tdef.name, tdef.parameters or {})  # noqa: N806
                        return _StructuredTool.from_function(
                            coroutine=_exec,
                            name=tdef.name,
                            description=tdef.description or "knowledge search",
                            args_schema=ArgsModel,
                        )

                    knowledge_adapters = [_mk_adapter(t) for t in knowledge_tools]

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
                        "instance_type": getattr(target_instance, "instance_type", None),
                        "name": getattr(target_instance, "name", None),
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

            # Defensive: if workflow build unexpectedly returned None, fall back to a direct LLM call
            if self.workflow is None or not hasattr(self.workflow, "compile"):
                logger.error(
                    "Workflow build returned None or invalid object; using direct LLM fallback."
                )
                try:
                    if self.progress_callback:
                        await self.progress_callback(
                            "Encountered workflow issue; falling back to direct LLM response.",
                            "agent_reflection",
                        )

                    # Direct LLM call without LangGraph execution; sanitize messages first
                    def _sanitize_messages_for_llm(msgs: list[BaseMessage]) -> list[BaseMessage]:
                        if not msgs:
                            return msgs
                        seen_tool_ids = set()
                        clean: list[BaseMessage] = []
                        for m in msgs:
                            if isinstance(m, AIMessage):
                                try:
                                    for tc in getattr(m, "tool_calls", []) or []:
                                        if isinstance(tc, dict):
                                            tid = tc.get("id") or tc.get("tool_call_id")
                                            if tid:
                                                seen_tool_ids.add(tid)
                                except Exception:
                                    pass
                                clean.append(m)
                            elif isinstance(m, ToolMessage) or getattr(m, "type", "") == "tool":
                                tid = getattr(m, "tool_call_id", None)
                                if tid and tid in seen_tool_ids:
                                    clean.append(m)
                                else:
                                    continue
                            else:
                                clean.append(m)
                        while clean and (
                            isinstance(clean[0], ToolMessage)
                            or getattr(clean[0], "type", "") == "tool"
                        ):
                            clean = clean[1:]
                        # If the last message is an assistant with unfulfilled tool_calls, drop it to avoid API 400
                        if (
                            clean
                            and isinstance(clean[-1], AIMessage)
                            and (getattr(clean[-1], "tool_calls", None) or [])
                        ):
                            clean = clean[:-1]
                        # Fallback guard: never return an empty list; keep first non-tool from original msgs
                        if not clean:
                            for m in msgs:
                                if not (
                                    isinstance(m, ToolMessage) or getattr(m, "type", "") == "tool"
                                ):
                                    clean = [m]
                                    break
                        return clean

                    safe_msgs = _sanitize_messages_for_llm(initial_messages)
                    _preflight_log(safe_msgs, "direct-fallback-before")
                    resp = await self._ainvoke_memo("agent", self.llm_with_tools, safe_msgs)
                    return str(getattr(resp, "content", resp) or "")
                except Exception as e:
                    logger.error(f"Direct LLM fallback failed: {e}")
                    raise

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

        # Fast skip: if response is clearly out of Redis scope and has no URLs, don't invoke LLM
        try:
            if not self._is_redis_scoped(response):
                import re as _re

                if not _re.search(r"https?://", response or "", flags=_re.IGNORECASE):
                    return {
                        "has_errors": False,
                        "validation_notes": "Skipped fact-check (out of Redis scope)",
                    }
        except Exception:
            # If scope check fails, proceed with normal flow
            pass

        try:
            import time as _time

            start_time = _time.monotonic()
            # URL validation disabled per user request
            url_validation_results = []

            # Create fact-checker LLM (separate from main agent)
            fact_checker = ChatOpenAI(
                model=self.settings.openai_model_mini,
                openai_api_key=self.settings.openai_api_key,
                timeout=self.settings.llm_timeout,
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
                    # Cap validation to a few commands to limit latency
                    unique_cmds = unique_cmds[:3]
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
                        if _time.monotonic() - start_time > 20.0:
                            lines.append(
                                "- Skipping remaining command validations due to time budget"
                            )
                            break
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

            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=FACT_CHECKER_PROMPT),
                HumanMessage(content=fact_check_input),
            ]

            # Retry fact-check with parsing
            async def _fact_check_with_retry():
                """Inner function for fact-check retry logic."""
                fact_check_response = await self._ainvoke_memo("fact_check", fact_checker, messages)

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
                    max_retries=1,
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
        """Process a query once, then attach Safety and Fact-Checking notes.

        No corrective re-runs are performed. The operator can review the notes.
        """
        # Initialize in-run caches (LLM memo; tool cache is per-ToolManager context)
        self._begin_run_cache()
        try:
            # Produce the primary response via the full workflow
            response = await self.process_query(
                query,
                session_id,
                user_id,
                max_iterations,
                context,
                progress_callback,
                conversation_history,
            )

            # Skip safety/fact-check entirely if out of Redis scope
            try:
                if not (self._is_redis_scoped(query) or self._is_redis_scoped(response)):
                    logger.info("Skipping safety/fact-check (out of Redis scope)")
                    return response
            except Exception:
                # If scope detection fails, proceed with notes
                pass

            # Collect notes (no corrections) in parallel
            safety_result, fact_check_result = await asyncio.gather(
                self._safety_evaluate_response(query, response),
                self._fact_check_response(response),
            )

            # Render natural-language notes and append to the response
            section = await self._render_safety_and_fact_check_section(
                safety_result=safety_result, fact_check_result=fact_check_result
            )
            if section.strip():
                return response + "\n\n" + section
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
                    status = getattr(e, "status_code", None) or getattr(
                        getattr(e, "response", None), "status_code", None
                    )
                    body = None
                    if hasattr(e, "body") and isinstance(getattr(e, "body"), (str, bytes)):
                        body = (
                            e.body.decode("utf-8", errors="ignore")
                            if isinstance(e.body, (bytes, bytearray))
                            else e.body
                        )
                    elif hasattr(e, "response") and getattr(e, "response") is not None:
                        resp = getattr(e, "response")
                        body = getattr(resp, "text", None) or getattr(resp, "content", None)
                        if isinstance(body, (bytes, bytearray)):
                            body = body.decode("utf-8", errors="ignore")
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

    async def _safety_evaluate_response(
        self, original_query: str, response: str, is_correction_recheck: bool = False
    ) -> Dict[str, Any]:
        r"""
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
        # Ground safety evaluation in Redis knowledge base; if no citations, consider safe
        _citations: list[dict] = []

        try:
            # Build a small set of focused queries from response content
            import re as _re
            topics: list[str] = []
            text = f"{original_query}\n{response}"[:4000]
            # Extract admin API endpoints and key terms
            endpoints = _re.findall(r"/v\d+/[a-zA-Z0-9_\-/]+", text)[:2]
            if endpoints:
                topics.extend([f"Redis Enterprise admin API {ep}" for ep in endpoints])
            if _re.search(r"\brladmin\b", text, flags=_re.IGNORECASE):
                topics.append("rladmin command safety")
            for kw in ["eviction", "persistence", "replication", "backup", "flushall", "CONFIG SET", "AOF", "RDB", "PUT", "PATCH", "DELETE"]:
                if kw.lower() in text.lower():
                    topics.append(f"Redis {kw} safety")
            # Dedup and cap
            seen = set()
            queries = []
            for t in topics:
                if t not in seen:
                    seen.add(t)
                    queries.append(t)
                if len(queries) >= 2:
                    break

            _citations: list[dict] = []
            if queries:
                from redis_sre_agent.core.knowledge_helpers import search_knowledge_base_helper
                for q in queries:
                    try:
                        res = await search_knowledge_base_helper(q, limit=3)
                        for r in res.get("results", [])[:2]:
                            src = r.get("source") or ""
                            if any(dom in src for dom in ("redis.io", "redis.com", "docs.redis.com", "redis.cloud")):
                                _citations.append({
                                    "source": src,
                                    "title": r.get("title", ""),
                                    "excerpt": (r.get("content") or "")[:280],
                                })
                            if len(_citations) >= 3:
                                break
                    except Exception:
                        continue

            if not _citations:
                # No authoritative Redis citations; proceed to evaluator with (none) so it defaults to safe
                _citations = []
        except Exception:
            # If grounding fails, proceed but still bias toward safety only with strong evidence
            _citations = []

        """
        safety_prompt = """
You are a Redis SRE Safety Evaluator. Evaluate ONLY using the provided Redis citations below.
If you cannot support a claim with a direct citation from these sources, mark the response as safe.

STRICT RULES:
- Use ONLY information from the citations (official Redis docs/KB): redis.io, docs.redis.com, redis.com, redis.cloud
- Do NOT apply generic HTTP/REST heuristics (e.g., "PUT replaces full resource") unless explicitly stated in the cited Redis docs
- Limit your scope to Redis, Redis Enterprise, and Redis Cloud features and tooling
- If the citations are silent/ambiguous, default to safe and do not invent risks

EVALUATE THIS RESPONSE FOR SERIOUS SAFETY CONCERNS:

ORIGINAL QUERY:
{original_query}

AGENT RESPONSE:
{response}

CITATIONS (authoritative context):
{citations}

Only flag as unsafe if the recommendations could cause (and citations clearly support):
1. Immediate data loss (e.g., destructive eviction on persistent stores)
2. Logic contradicting documented usage patterns or safety notes
3. System failure (operations that would crash/corrupt Redis) per docs

Do NOT flag as unsafe:
- Recommendations with appropriate warnings documented in the citations
- Restart/snapshot/persistence changes when the cited docs describe safe procedures
- Operational risks not documented as unsafe in Redis sources

RESPONSE FORMAT (JSON):
{{
  "safe": true/false,
  "risk_level": "low|medium|high|critical",
  "violations": ["each violation must have a supporting citation"],
  "corrective_guidance": "safe alternative steps from citations",
  "reasoning": "concise, cite-based explanation",
  "citations": [
    {{"url": "...", "quote": "short relevant excerpt"}}
  ]
}}

{"CORRECTION RECHECK: This is a safety recheck of a corrected response. Be more lenient - if the response includes appropriate warnings and safer alternatives supported by the citations, consider it safe." if is_correction_recheck else ""}
"""

        # Pre-format the safety prompt with safe strings and citations to avoid closure issues
        def _safe_str(obj):
            try:
                return str(obj)
            except Exception:
                return repr(obj)

        query_str = _safe_str(original_query)
        response_str = _safe_str(response)
        citations_text = "(none)"
        formatted_prompt = safety_prompt.replace("{original_query}", query_str)
        formatted_prompt = formatted_prompt.replace("{response}", response_str)
        formatted_prompt = formatted_prompt.replace("{citations}", citations_text or "(none)")
        safety_llm = ChatOpenAI(
            model=self.settings.openai_model_mini,
            openai_api_key=self.settings.openai_api_key,
            timeout=self.settings.llm_timeout,
        )

        async def _evaluate_with_retry():
            """Inner function for retry logic."""
            safety_response = await self._ainvoke_memo(
                "safety", safety_llm, [SystemMessage(content=formatted_prompt)]
            )
            # Parse the JSON response - this will raise JSONDecodeError if parsing fails
            result = json.loads(safety_response.content)
            return result

        try:
            # Use retry logic for both LLM call and JSON parsing
            result = await self._retry_with_backoff(
                _evaluate_with_retry,
                max_retries=1,
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
