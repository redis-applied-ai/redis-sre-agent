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

from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from ..helpers import parse_json_maybe_fenced


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
        resp = await knowledge_llm.ainvoke(state.get("messages", []))
        return {
            "messages": state.get("messages", []) + [resp],
            "budget": int(state.get("budget", max_tool_steps)),
        }

    async def tools_node(state: PState) -> PState:
        # Execute allowed tools through ToolNode; decrement budget safely
        out = await tool_node.ainvoke({"messages": state.get("messages", [])})
        messages = out.get("messages", state.get("messages", []))
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
        # Parse plan JSON from the last AI message; tolerate fenced JSON
        msgs = state.get("messages", [])
        last_ai: Optional[AIMessage] = None
        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                last_ai = m
                break
        content = (getattr(last_ai, "content", "") or "").strip()
        plan: Dict[str, Any] = {}
        try:
            plan = parse_json_maybe_fenced(content)
            if not isinstance(plan, dict):
                plan = {"raw": plan}
        except Exception:
            # Fall back to empty plan; parent can handle failure
            plan = {"summary": "planning_failed", "raw": content[:2000]}
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
