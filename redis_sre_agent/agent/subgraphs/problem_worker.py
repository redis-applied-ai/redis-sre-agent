"""
Per-problem worker subgraph for knowledge-only research and plan synthesis.

This subgraph encapsulates a small LLM → ToolNode → LLM loop with an explicit
step budget, then emits a structured plan result parsed from the final LLM
message content.

It is intentionally generic so it can be reused from the main agent by
preparing the initial state messages (system+human with problem context)
and passing only knowledge_* tools.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from ..helpers import log_preflight_messages, parse_json_maybe_fenced, sanitize_messages_for_llm

logger = logging.getLogger(__name__)


class PState(TypedDict, total=False):
    messages: List[BaseMessage]
    budget: int
    result: Dict[str, Any]


def build_problem_worker(knowledge_llm, knowledge_tools: List[Any], max_tool_steps: int = 3):
    """Build and compile the per-problem worker subgraph.

    Args:
        knowledge_llm: An LLM bound for knowledge/search operations
        knowledge_tools: Tools limited to knowledge_* (search, retrieval, etc.)
        max_tool_steps: Maximum number of tool executions before synthesis

    Returns:
        A compiled graph runnable with .invoke/.ainvoke that accepts PState and
        returns PState including a "result" dict containing the synthesized plan.
    """
    tool_node = ToolNode(knowledge_tools)

    async def llm_node(state: PState) -> PState:
        msgs = sanitize_messages_for_llm(state.get("messages", []))
        # Preflight log (centralized)
        log_preflight_messages(msgs, label="ProblemWorker preflight LLM", logger=logger)
        resp = await knowledge_llm.ainvoke(msgs)
        return {
            "messages": msgs + [resp],
            "budget": int(state.get("budget", max_tool_steps)),
        }

    async def tools_node(state: PState) -> PState:
        # Execute allowed tools through ToolNode; decrement budget safely
        prev = state.get("messages", [])
        # Preflight log (centralized)
        log_preflight_messages(prev, label="ProblemWorker preflight ToolNode", logger=logger)
        out = await tool_node.ainvoke({"messages": prev})
        out_msgs = out.get("messages", [])
        # Append only ToolMessages to preserve full prior window
        from langchain_core.messages import ToolMessage as _TM  # noqa: N814

        delta = [m for m in out_msgs if isinstance(m, _TM)]
        messages = prev + delta if delta else prev
        budget = max(0, int(state.get("budget", max_tool_steps)) - 1)
        return {"messages": messages, "budget": budget}

    def should_continue(state: PState) -> str:
        # Continue to tools if last AI message requested tools and we have budget
        msgs = state.get("messages", [])
        last_ai: Optional[AIMessage] = None
        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                last_ai = m
                break
        has_calls = bool(getattr(last_ai, "tool_calls", None))
        budget_left = int(state.get("budget", max_tool_steps)) > 0
        return "tools" if (has_calls and budget_left) else "synth"

    def synth_node(state: PState) -> PState:
        # Synthesize a result from the last AI message.
        # Prefer natural language output; if JSON is present, parse it, but always
        # include the full narrative so callers can use it directly.
        msgs = state.get("messages", [])
        last_ai: Optional[AIMessage] = None
        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                last_ai = m
                break
        content = (getattr(last_ai, "content", "") or "").strip()
        plan: Dict[str, Any] = {}
        try:
            parsed = parse_json_maybe_fenced(content)
            plan = parsed if isinstance(parsed, dict) else {}
        except Exception:
            # Parsing failed; emit a structured fallback
            plan = {"summary": "planning_failed", "raw": content}
        # Always carry the narrative; ensure we have a summary string
        plan["narrative"] = content
        if not isinstance(plan.get("summary"), str) or not plan.get("summary"):
            # Use the first ~1000 chars of the narrative as summary
            plan["summary"] = content[:1000]
        return {"messages": msgs, "budget": int(state.get("budget", 0)), "result": plan}

    g = StateGraph(PState)
    g.add_node("llm", llm_node)
    g.add_node("tools", tools_node)
    g.add_node("synth", synth_node)

    g.set_entry_point("llm")
    g.add_conditional_edges("llm", should_continue, {"tools": "tools", "synth": "synth"})
    g.add_edge("tools", "llm")
    g.add_edge("synth", END)

    return g.compile()
