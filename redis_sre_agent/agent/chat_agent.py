"""
Lightweight Chat Agent for fast Redis instance interaction.

This agent is designed for quick Q&A when a Redis instance is available
but the user doesn't need a full health check or triage. It has access
to all Redis tools but uses a simpler workflow without deep research
or safety-evaluation chains.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, NotRequired, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode as LGToolNode
from opentelemetry import trace

from redis_sre_agent.core.clusters import RedisCluster
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.llm_helpers import create_llm, create_mini_llm
from redis_sre_agent.core.progress import (
    NullEmitter,
    ProgressEmitter,
)
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.models import ToolCapability

if TYPE_CHECKING:
    from pathlib import Path

from .helpers import build_result_envelope
from .knowledge_context import build_startup_knowledge_context
from .models import AgentResponse

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


CHAT_SYSTEM_PROMPT = """You are a Redis SRE agent with access to tools for investigating Redis deployments.

## Your Approach - ITERATIVE INVESTIGATION

Work step by step. Don't try to gather all information at once.

1. **Make a few targeted tool calls** (2-4 max per turn)
2. **Analyze the results** - think about what you learned
3. **Decide what to do next** - either answer or make more targeted calls
4. **Repeat** until you have enough information to answer

This iterative approach prevents overwhelming context limits and produces better analysis.

## Tool Calling Guidelines

**Per turn, call at most 3-4 tools.** Analyze results before calling more.

For Redis diagnostics:
- Start with diagnostics-category tools for a comprehensive overview
- Add diagnostics/admin-api category tools for Redis Enterprise/Cloud configuration details
- Add knowledge-category tools when you need troubleshooting guidance

For code/repo investigation:
- **First:** One targeted repos-category search with a specific query
- **Analyze:** Look at search results, identify the most relevant file
- **Then:** Fetch one relevant file from repos-category tools
- **Repeat:** If needed, fetch another file based on what you learned

For metrics/logs:
- Be specific with queries - broad queries return too much data
- Fetch one metric or log query at a time

For historical incident context (if `tickets` tools are available):
- Use tickets tools instead of general knowledge search because general knowledge search excludes support tickets
- Search support tickets with concrete identifiers (cluster name/host, error strings)
- Fetch the most relevant ticket record for full details

Only call categories that are available in your current tool list.

## What NOT to Do

- ❌ Don't call 5+ tools in parallel
- ❌ Don't run multiple variations of the same search
- ❌ Don't fetch multiple files at once - read one, analyze, then decide if you need more
- ❌ Don't try to gather everything upfront

## Guidelines
- Answer questions iteratively - it's OK to take multiple turns
- Start with the most likely source of relevant info
- Be conversational about what you're finding and what you'll check next
- For truly exhaustive multi-topic analysis, suggest "deep triage"

## Redis Enterprise / Redis Cloud Notes
- For managed Redis, INFO output can be misleading
- Use available diagnostics/admin-api tools for accurate configuration details
- Don't suggest CONFIG SET for managed deployments
"""


class ChatAgentState(TypedDict):
    """State for the chat agent."""

    messages: List[BaseMessage]
    session_id: str
    user_id: str
    current_tool_calls: List[Dict[str, Any]]
    iteration_count: int
    max_iterations: int
    startup_system_prompt: Optional[str]
    startup_prompt_initialized: NotRequired[bool]
    toolset_generation: NotRequired[int]
    # Accumulated tool result envelopes for context management and citation derivation
    signals_envelopes: List[Dict[str, Any]]


class ChatAgent:
    """Lightweight LangGraph-based agent for quick Redis Q&A.

    This agent has access to all Redis tools but uses a simpler workflow
    optimized for fast, targeted responses rather than comprehensive triage.
    """

    # Threshold for summarizing tool outputs (chars)
    ENVELOPE_SUMMARY_THRESHOLD = 500

    def __init__(
        self,
        redis_instance: Optional[RedisInstance] = None,
        redis_cluster: Optional[RedisCluster] = None,
        progress_emitter: Optional[ProgressEmitter] = None,
        exclude_mcp_categories: Optional[List["ToolCapability"]] = None,
        support_package_path: Optional["Path"] = None,
    ):
        """Initialize the Chat agent.

        Args:
            redis_instance: Optional Redis instance for context
            redis_cluster: Optional Redis cluster for cluster-scoped context
            progress_emitter: Emitter for progress/notification updates
            exclude_mcp_categories: Optional list of MCP tool capability categories to exclude.
                Use this to filter out specific types of MCP tools. Common categories:
                METRICS, LOGS, TICKETS, REPOS, TRACES, DIAGNOSTICS, KNOWLEDGE, UTILITIES.
            support_package_path: Optional path to an extracted support package.
                When provided, loads tools for analyzing logs, diagnostics, and
                Redis data from the package.
        """
        self.settings = settings
        self.redis_instance = redis_instance
        self.redis_cluster = redis_cluster
        self.exclude_mcp_categories = exclude_mcp_categories
        self.support_package_path = support_package_path

        self._emitter = progress_emitter if progress_emitter is not None else NullEmitter()

        self.llm = create_llm()
        self.mini_llm = create_mini_llm()

        logger.info(
            f"Chat agent initialized (instance: {redis_instance.name if redis_instance else 'none'})"
        )

    def _build_expand_evidence_tool(
        self,
        envelopes_container: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Build a tool that allows the LLM to retrieve full tool output details.

        When we summarize tool outputs, the LLM only sees condensed versions.
        This tool lets the LLM request the full original output for any tool_key
        if it needs more detail. Supports optional JMESPath queries for extracting
        specific data.

        The tool is available from the start but references a mutable container
        that gets populated as tool calls complete. This ensures the LLM knows
        the tool exists and can plan to use it after making other tool calls.

        Args:
            envelopes_container: A mutable dict with "envelopes" key that gets
                                 updated as tool calls complete

        Returns:
            A dict with name, description, func, and parameters for creating a tool
        """
        import jmespath
        from jmespath.exceptions import JMESPathError

        def expand_evidence(tool_key: str, query: Optional[str] = None) -> Dict[str, Any]:
            """Retrieve full or queried data from a previous tool call.

            Args:
                tool_key: The tool_key from a summarized evidence item
                query: Optional JMESPath expression to extract specific data
            """
            # Get current envelopes from the mutable container
            envelopes = envelopes_container.get("envelopes", [])
            originals_by_key = {e.get("tool_key"): e for e in envelopes}
            available_keys = list(originals_by_key.keys())

            if not available_keys:
                return {
                    "status": "error",
                    "error": (
                        "No tool calls have been made yet. "
                        "First call other tools to gather data, then use expand_evidence "
                        "to retrieve or query their results."
                    ),
                }

            if tool_key not in originals_by_key:
                return {
                    "status": "error",
                    "error": f"Unknown tool_key: '{tool_key}'. Available tool_keys: {available_keys}. "
                    "Use one of the available tool_keys from a previous tool call.",
                }
            original = originals_by_key[tool_key]
            data = original.get("data", {})

            # If query is provided, use JMESPath to extract data
            if query:
                try:
                    queried_data = jmespath.search(query, data)
                    return {
                        "status": "success",
                        "tool_key": tool_key,
                        "name": original.get("name"),
                        "query": query,
                        "queried_data": queried_data,
                    }
                except JMESPathError as e:
                    # Provide helpful error with syntax hints
                    return {
                        "status": "error",
                        "error": f"Invalid JMESPath query '{query}': {e}. "
                        "JMESPath syntax tips: "
                        "- Access nested fields: 'field.subfield' "
                        "- Get all items from array field: 'results[*].fieldname' "
                        "- Slice arrays: 'items[:5]' (first 5) or 'items[-3:]' (last 3) "
                        "- Filter: 'items[?score > `0.5`]' (note: numbers need backticks) "
                        "- Project multiple fields: 'results[*].{name: title, url: source}'",
                    }

            # No query - return full data
            return {
                "status": "success",
                "tool_key": tool_key,
                "name": original.get("name"),
                "full_data": data,
            }

        return {
            "name": "expand_evidence",
            "description": (
                "Retrieve or query data from a previous tool call using JMESPath. "
                "IMPORTANT: The tool_key parameter must be the exact function name you called "
                "(e.g., 'knowledge_abc123_search', 'redis_info'), NOT document IDs, Redis keys, "
                "or any values from inside the tool's results. "
                "JMESPath examples: 'results[*].title' extracts all titles, "
                "'entries[:3]' gets first 3 items, "
                "'items[?score > `0.8`]' filters by condition."
            ),
            "func": expand_evidence,
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_key": {
                        "type": "string",
                        "description": (
                            "The exact function name you previously called (e.g., 'knowledge_abc123_search', "
                            "'redis_info'). This is the tool/function name from your tool call, NOT a "
                            "document ID, Redis key, or value from inside the results."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "JMESPath expression to extract specific data. "
                            "Common patterns: "
                            "'fieldname' - get a field, "
                            "'results[*].title' - extract field from all array items, "
                            "'results[:5]' - first 5 items, "
                            "'results[?score > `0.5`]' - filter (numbers in backticks), "
                            "'results[*].{name: title, link: source}' - project/rename fields. "
                            "Omit to get full data."
                        ),
                    },
                },
                "required": ["tool_key"],
            },
        }

    def _tool_call_progress_message(
        self,
        tool_mgr: ToolManager,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> str:
        """Build the user-facing progress message for a tool call."""
        status_msg = tool_mgr.get_status_update(tool_name, tool_args)
        if status_msg:
            return status_msg

        if tool_name == "expand_evidence":
            query = str(tool_args.get("query") or "").strip()
            message = (
                "I have a preview of the last tool call's output. "
                "I'm retrieving the full output now."
            )
            if query:
                message += f" Applying JMESPath query: {query}"
            return message

        return f"Executing tool: {tool_name}"

    def _summarize_envelope_sync(self, env: Dict[str, Any]) -> Dict[str, Any]:
        """Set summary field for large envelope data, preserving full data.

        For chat agent, we use simple truncation rather than LLM summarization
        to keep things fast. The full `data` is always preserved for:
        - Decision traces (`task trace` CLI)
        - The `expand_evidence` tool
        - Future query capabilities
        """
        data_str = json.dumps(env.get("data", {}), default=str)
        if len(data_str) <= self.ENVELOPE_SUMMARY_THRESHOLD:
            return env

        # Set summary, keep full data
        env = dict(env)  # Copy to avoid mutating original
        env["summary"] = (
            data_str[: self.ENVELOPE_SUMMARY_THRESHOLD]
            + f"... (use expand_evidence for full {len(data_str)} chars)"
        )
        return env

    def _create_summarized_tool_message(
        self, original_msg: ToolMessage, tool_key: str, data: Dict[str, Any]
    ) -> ToolMessage:
        """Create a summarized ToolMessage for the LLM when data is large.

        The LLM receives a preview with structure hints and instructions on how
        to use expand_evidence to get full data or query specific fields.
        """
        data_str = json.dumps(data, default=str)
        total_size = len(data_str)

        if total_size <= self.ENVELOPE_SUMMARY_THRESHOLD:
            # Small enough - return original message unchanged
            return original_msg

        # Build a helpful preview showing structure
        preview_lines = []

        # WARNING and instructions FIRST - most important info at top
        preview_lines.append(f"⚠️ LARGE RESULT ({total_size:,} chars) - DATA TRUNCATED")
        preview_lines.append("You are NOT seeing the full data. Use expand_evidence to access it:")
        preview_lines.append(f"  expand_evidence(tool_key='{tool_key}')")
        preview_lines.append(f"  expand_evidence(tool_key='{tool_key}', query='results[*].source')")
        preview_lines.append("")

        # Show structure: top-level keys and their types/sizes
        if isinstance(data, dict):
            preview_lines.append("Data structure:")
            for key, value in list(data.items())[:10]:  # First 10 keys
                if isinstance(value, list) and len(value) > 0:
                    # Show list length AND first item's keys if it's a dict
                    if isinstance(value[0], dict):
                        item_keys = list(value[0].keys())[:8]
                        preview_lines.append(
                            f"  {key}: [{len(value)} items] each with keys: {item_keys}"
                        )
                    else:
                        preview_lines.append(f"  {key}: [{len(value)} items]")
                elif isinstance(value, list):
                    preview_lines.append(f"  {key}: [empty]")
                elif isinstance(value, dict):
                    preview_lines.append(f"  {key}: {{...}}")
                elif isinstance(value, str) and len(value) > 50:
                    preview_lines.append(f'  {key}: "{value[:50]}..."')
                else:
                    val_str = json.dumps(value, default=str)
                    if len(val_str) > 60:
                        val_str = val_str[:60] + "..."
                    preview_lines.append(f"  {key}: {val_str}")

        # Brief preview of the data
        preview_lines.append("")
        preview_lines.append(f"Preview (first {self.ENVELOPE_SUMMARY_THRESHOLD} chars):")
        preview_lines.append(data_str[: self.ENVELOPE_SUMMARY_THRESHOLD] + "...")

        summarized_content = "\n".join(preview_lines)

        return ToolMessage(
            content=summarized_content,
            tool_call_id=original_msg.tool_call_id,
            name=original_msg.name if hasattr(original_msg, "name") else None,
        )

    def _build_workflow(
        self,
        tool_mgr: ToolManager,
        emitter: Optional[ProgressEmitter] = None,
    ) -> StateGraph:
        """Build the LangGraph workflow for chat interactions.

        Args:
            tool_mgr: ToolManager instance for resolving tool calls
            emitter: Optional progress emitter for status updates
        """
        # Mutable container for envelopes - expand_evidence references this
        # so it can access envelopes as they're added by tool calls
        envelopes_container: Dict[str, List[Dict[str, Any]]] = {"envelopes": []}
        runtime_tools_by_generation: Dict[int, Dict[str, Any]] = {}

        async def ensure_runtime_tools(
            requested_generation: Optional[int] = None,
        ) -> Dict[str, Any]:
            current_generation = tool_mgr.get_toolset_generation()
            generation = (
                requested_generation if requested_generation is not None else current_generation
            )
            cached = runtime_tools_by_generation.get(generation)
            if cached is not None:
                return cached

            if requested_generation is not None and requested_generation != current_generation:
                logger.warning(
                    "Requested chat tool generation %s is unavailable; using current generation %s",
                    requested_generation,
                    current_generation,
                )
                generation = current_generation
                cached = runtime_tools_by_generation.get(generation)
                if cached is not None:
                    return cached

            from .helpers import build_adapters_for_tooldefs as _build_adapters

            tooldefs = tool_mgr.get_tools()
            adapters = await _build_adapters(tool_mgr, tooldefs)
            expand_spec = self._build_expand_evidence_tool(envelopes_container)
            expand_tool = StructuredTool.from_function(
                func=expand_spec["func"],
                name=expand_spec["name"],
                description=expand_spec["description"],
            )
            all_adapters = list(adapters) + [expand_tool]
            runtime = {
                "generation": generation,
                "tooldefs_by_name": {t.name: t for t in tooldefs},
                "all_adapters": all_adapters,
                "llm_with_expand": self.llm.bind_tools(all_adapters),
                "tool_node": LGToolNode(all_adapters),
            }
            runtime_tools_by_generation[generation] = runtime
            return runtime

        async def agent_node(state: ChatAgentState) -> Dict[str, Any]:
            """Main agent node - invokes LLM with tools."""
            runtime = await ensure_runtime_tools()
            tooldefs_by_name = runtime["tooldefs_by_name"]
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            startup_system_prompt = state.get("startup_system_prompt")
            startup_prompt_initialized = state.get("startup_prompt_initialized", False)

            if (
                startup_system_prompt is None
                and messages
                and isinstance(messages[0], SystemMessage)
            ):
                startup_system_prompt = str(messages[0].content or "")
                startup_prompt_initialized = True

            if not messages or not isinstance(messages[0], SystemMessage):
                if startup_system_prompt is None or (
                    iteration_count == 0 and not startup_prompt_initialized
                ):
                    context_query = ""
                    for message in reversed(messages):
                        if isinstance(message, HumanMessage):
                            context_query = str(message.content or "")
                            break

                    startup_context = await build_startup_knowledge_context(
                        query=context_query,
                        version="latest",
                        available_tools=list(tooldefs_by_name.values()),
                    )
                    startup_system_prompt = (
                        f"{startup_context}\n\n{CHAT_SYSTEM_PROMPT}"
                        if startup_context.strip()
                        else CHAT_SYSTEM_PROMPT
                    )
                    startup_prompt_initialized = True
                startup_system_prompt = startup_system_prompt or CHAT_SYSTEM_PROMPT
                messages = [SystemMessage(content=startup_system_prompt)] + messages

            with tracer.start_as_current_span("chat_agent_node"):
                response = await runtime["llm_with_expand"].ainvoke(messages)

            # Persist only the original workflow state messages plus response.
            # If we injected a SystemMessage just for this invocation, keep it ephemeral.
            new_messages = list(state["messages"]) + [response]
            return {
                "messages": new_messages,
                "iteration_count": iteration_count + 1,
                "startup_system_prompt": startup_system_prompt,
                "startup_prompt_initialized": startup_prompt_initialized,
                "toolset_generation": runtime["generation"],
                "current_tool_calls": response.tool_calls
                if hasattr(response, "tool_calls")
                else [],
            }

        async def tool_node(state: ChatAgentState) -> Dict[str, Any]:
            """Execute tool calls from the agent."""
            runtime = await ensure_runtime_tools(state.get("toolset_generation"))
            tooldefs_by_name = runtime["tooldefs_by_name"]
            messages = state["messages"]
            envelopes = list(state.get("signals_envelopes") or [])

            # Get pending tool calls from the last AI message
            last_msg = messages[-1] if messages else None
            tool_calls = []
            if isinstance(last_msg, AIMessage) and hasattr(last_msg, "tool_calls"):
                tool_calls = last_msg.tool_calls or []

            # Emit progress updates for each tool call
            if emitter and tool_calls:
                for tc in tool_calls:
                    tool_name = (
                        tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    )
                    tool_args = (
                        tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    ) or {}
                    if tool_name:
                        status_msg = self._tool_call_progress_message(
                            tool_mgr, tool_name, tool_args
                        )
                        await emitter.emit(status_msg, "tool_call")

            with tracer.start_as_current_span("chat_tool_node"):
                out = await runtime["tool_node"].ainvoke({"messages": messages})
                out_messages = out.get("messages", [])
                new_tool_messages = [m for m in out_messages if isinstance(m, ToolMessage)]

                # Build envelopes and create summarized messages for the LLM
                # The LLM sees summarized versions; full data stays in envelopes
                messages_for_llm: List[ToolMessage] = []

                for idx, tc in enumerate(tool_calls):
                    tool_name = (
                        tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    )
                    tool_args = (
                        tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    ) or {}

                    tm = new_tool_messages[idx] if idx < len(new_tool_messages) else None
                    if tm is None:
                        continue

                    # Skip expand_evidence calls - pass through unchanged
                    if tool_name == "expand_evidence":
                        messages_for_llm.append(tm)
                        continue

                    env_dict = build_result_envelope(
                        tool_name or f"tool_{idx + 1}", tool_args, tm, tooldefs_by_name
                    )

                    # Summarize envelope (preserves full data, adds summary field)
                    env_dict = self._summarize_envelope_sync(env_dict)
                    envelopes.append(env_dict)

                    # Create summarized message for LLM if data is large
                    tool_key = env_dict.get("tool_key", tool_name)
                    data = env_dict.get("data", {})
                    summarized_msg = self._create_summarized_tool_message(tm, tool_key, data)
                    messages_for_llm.append(summarized_msg)

                    # Log summarization for debugging
                    orig_len = len(tm.content) if hasattr(tm, "content") else 0
                    summ_len = (
                        len(summarized_msg.content) if hasattr(summarized_msg, "content") else 0
                    )
                    if orig_len != summ_len:
                        logger.debug(
                            f"Summarized tool result: {tool_key} "
                            f"({orig_len:,} -> {summ_len:,} chars)"
                        )

                # Update the mutable container so expand_evidence can see new envelopes
                envelopes_container["envelopes"] = envelopes

            return {
                "messages": list(messages) + messages_for_llm,
                "current_tool_calls": [],
                "toolset_generation": runtime["generation"],
                "signals_envelopes": envelopes,
            }

        def should_continue(state: ChatAgentState) -> str:
            """Decide whether to continue with tools or end."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            max_iterations = state.get("max_iterations", 10)

            if iteration_count >= max_iterations:
                logger.warning(f"Chat agent reached max iterations ({max_iterations})")
                return END

            if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
                return "tools"

            if state.get("current_tool_calls"):
                return "tools"

            return END

        workflow = StateGraph(ChatAgentState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        workflow.add_edge("tools", "agent")

        return workflow

    async def process_query(
        self,
        query: str,
        session_id: str,
        user_id: str,
        max_iterations: int = 10,
        context: Optional[Dict[str, Any]] = None,
        progress_emitter: Optional[ProgressEmitter] = None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> AgentResponse:
        """Process a query with quick tool access.

        Args:
            query: User's question
            session_id: Session identifier
            user_id: User identifier
            max_iterations: Maximum agent iterations (default 10)
            context: Additional context (e.g., instance_id)
            progress_emitter: Emitter for progress/notification updates
            conversation_history: Optional previous messages for context

        Returns:
            AgentResponse with response text and any knowledge search results used
        """
        logger.info(f"Chat agent processing query for user {user_id}")

        # Use provided emitter, or fall back to instance emitter
        emitter = progress_emitter if progress_emitter is not None else self._emitter

        # Get cache client if tool caching is enabled
        cache_client = None
        if settings.tool_cache_enabled and self.redis_instance:
            cache_client = get_redis_client()
            logger.info(f"Tool caching enabled for instance {self.redis_instance.id}")

        # Create ToolManager with Redis instance for full tool access
        async with ToolManager(
            redis_instance=self.redis_instance,
            redis_cluster=self.redis_cluster,
            exclude_mcp_categories=self.exclude_mcp_categories,
            support_package_path=self.support_package_path,
            cache_client=cache_client,
            cache_ttl_overrides=settings.tool_cache_ttl_overrides or None,
            thread_id=session_id,
            task_id=(context or {}).get("task_id"),
            user_id=user_id,
        ) as tool_mgr:
            tools = tool_mgr.get_tools()
            logger.info(f"Chat agent loaded {len(tools)} tools")
            workflow = self._build_workflow(tool_mgr, emitter)

            checkpointer = MemorySaver()
            app = workflow.compile(checkpointer=checkpointer)

            # Build initial messages with shared startup context (pinned docs, skills, tool usage)
            startup_context = await build_startup_knowledge_context(
                query=query,
                version="latest",
                available_tools=tools,
            )
            system_prompt = (
                f"{startup_context}\n\n{CHAT_SYSTEM_PROMPT}"
                if startup_context.strip()
                else CHAT_SYSTEM_PROMPT
            )
            initial_messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]

            # Add instance context to the query if available
            enhanced_query = query
            if self.redis_instance:
                repo_context = ""
                if self.redis_instance.repo_url:
                    repo_context = f"""- Repository URL: {self.redis_instance.repo_url}

If you have GitHub tools available, you can search the repository for code, configuration, or documentation related to this Redis instance.
"""
                instance_context = f"""
INSTANCE CONTEXT: This query is about Redis instance:
- Instance Name: {self.redis_instance.name}
- Environment: {self.redis_instance.environment}
- Usage: {self.redis_instance.usage}
- Instance Type: {self.redis_instance.instance_type}
{repo_context}
Your diagnostic tools are PRE-CONFIGURED for this instance.

User Query: {query}"""
                enhanced_query = instance_context
            elif self.redis_cluster:
                cluster_context = f"""
CLUSTER CONTEXT: This query is about Redis cluster:
- Cluster Name: {self.redis_cluster.name}
- Cluster ID: {self.redis_cluster.id}
- Environment: {self.redis_cluster.environment}
- Cluster Type: {self.redis_cluster.cluster_type}

Cluster-level admin tools are PRE-CONFIGURED for this cluster when available.

User Query: {query}"""
                enhanced_query = cluster_context

            if conversation_history:
                initial_messages.extend(conversation_history)

            initial_messages.append(HumanMessage(content=enhanced_query))

            initial_state: ChatAgentState = {
                "messages": initial_messages,
                "session_id": session_id,
                "user_id": user_id,
                "current_tool_calls": [],
                "iteration_count": 0,
                "max_iterations": max_iterations,
                "startup_system_prompt": system_prompt,
                "startup_prompt_initialized": True,
                "toolset_generation": 0,
                "signals_envelopes": [],  # Track tool outputs - citations derived via extract_citations()
            }

            thread_config = {"configurable": {"thread_id": session_id}}

            try:
                await emitter.emit("Chat agent processing your question...", "agent_start")

                final_state = await app.ainvoke(initial_state, config=thread_config)

                # Get tool envelopes - AgentResponse derives search_results from these
                tool_envelopes = final_state.get("signals_envelopes", [])

                messages = final_state.get("messages", [])
                if messages:
                    last_message = messages[-1]
                    if isinstance(last_message, AIMessage):
                        return AgentResponse(
                            response=last_message.content,
                            tool_envelopes=tool_envelopes,
                        )
                    return AgentResponse(
                        response=str(last_message.content),
                        tool_envelopes=tool_envelopes,
                    )

                return AgentResponse(
                    response="I couldn't process that query. Please try rephrasing.",
                )

            except Exception as e:
                logger.exception(f"Chat agent error: {e}")
                return AgentResponse(response=f"Error processing query: {e}")


# Singleton cache keyed by instance name
_chat_agents: Dict[str, ChatAgent] = {}


def get_chat_agent(
    redis_instance: Optional[RedisInstance] = None,
    redis_cluster: Optional[RedisCluster] = None,
) -> ChatAgent:
    """Get or create a chat agent, optionally for a specific Redis instance.

    Args:
        redis_instance: Optional Redis instance for context
        redis_cluster: Optional Redis cluster for cluster-scoped context

    Returns:
        ChatAgent instance
    """
    global _chat_agents
    if redis_instance and redis_cluster:
        key = f"instance:{redis_instance.id}|cluster:{redis_cluster.id}"
    elif redis_instance:
        key = f"instance:{redis_instance.id}"
    elif redis_cluster:
        key = f"cluster:{redis_cluster.id}"
    else:
        key = "__no_instance__"

    if key not in _chat_agents:
        _chat_agents[key] = ChatAgent(
            redis_instance=redis_instance,
            redis_cluster=redis_cluster,
        )

    return _chat_agents[key]
