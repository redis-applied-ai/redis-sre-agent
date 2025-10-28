"""
Per-topic recommendation worker with a short knowledge-search loop and structured synthesis.

This worker receives a Topic (id/title/category/scope/narrative) and a list of
ResultEnvelope objects (evidence), plus instance facts. It can call knowledge_* tools
(2-3 steps) and then returns a structured Recommendation consisting of human-friendly
steps, optional plain-string command/api examples, and citations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from ..helpers import log_preflight_messages, sanitize_messages_for_llm
from ..models import Recommendation

logger = logging.getLogger(__name__)


class RecState(TypedDict, total=False):
    messages: List[BaseMessage]
    budget: int
    topic: Dict[str, Any]
    evidence: List[Dict[str, Any]]
    instance: Dict[str, Any]
    result: Dict[str, Any]


def build_recommendation_worker(
    base_llm,
    knowledge_tool_adapters: List[Any],
    *,
    max_tool_steps: int = 3,
    memoize=None,
):
    """Build a compiled subgraph for per-topic recommendations.

    Args:
        base_llm: Chat model used for both research and structured synthesis.
        knowledge_tool_adapters: Tools limited to knowledge_* (search/retrieval) operations.
        max_tool_steps: Budget for knowledge tool calls.
        memoize: Optional memoization callback with signature (tag, llm, messages) -> result

    Returns:
        A compiled runnable that accepts a dict state with keys:
          - topic: Topic (dict-like)
          - evidence: List[ResultEnvelope-like dicts]
          - instance: Optional[dict] of instance facts
        and returns state with key "result" containing a Recommendation dict.
    """

    tool_node = ToolNode(knowledge_tool_adapters)

    async def llm_node(state: RecState) -> RecState:
        messages = sanitize_messages_for_llm(state.get("messages", []))
        # Preflight log (centralized)
        log_preflight_messages(messages, label="RecWorker preflight LLM", logger=logger)
        if memoize:
            resp = await memoize("rec_worker_llm", base_llm, messages)
        else:
            resp = await base_llm.ainvoke(messages)
        out: RecState = {
            "messages": messages + [resp],
            "budget": int(state.get("budget", max_tool_steps)),
            "topic": state.get("topic"),
            "evidence": state.get("evidence", []),
            "instance": state.get("instance"),
        }
        return out

    async def tools_node(state: RecState) -> RecState:
        prev = state.get("messages", [])
        # Preflight log (centralized)
        log_preflight_messages(prev, label="RecWorker preflight ToolNode", logger=logger)
        out = await tool_node.ainvoke({"messages": prev})
        out_msgs = out.get("messages", [])
        from langchain_core.messages import ToolMessage as _TM  # noqa: N814

        delta = [m for m in out_msgs if isinstance(m, _TM)]
        messages = prev + delta if delta else prev
        budget = max(0, int(state.get("budget", max_tool_steps)) - 1)
        return {
            "messages": messages,
            "budget": budget,
            "topic": state.get("topic"),
            "evidence": state.get("evidence", []),
            "instance": state.get("instance"),
        }

    def should_continue(state: RecState) -> str:
        msgs = state.get("messages", [])
        # Find last AI message and check if it requested tools
        last_ai: Optional[AIMessage] = None
        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                last_ai = m
                break
        has_calls = bool(getattr(last_ai, "tool_calls", None))
        budget_left = int(state.get("budget", max_tool_steps)) > 0
        return "tools" if (has_calls and budget_left) else "synth"

    async def synth_node(state: RecState) -> RecState:
        # Final structured synthesis without further tool calls.
        # Build a focused prompt that includes the topic and evidence envelopes.
        topic = state.get("topic") or {}
        evidence = state.get("evidence", [])
        instance = state.get("instance") or {}

        # Use structured output to eliminate brittle JSON parsing
        structured_llm = base_llm.with_structured_output(Recommendation)

        sys = SystemMessage(
            content=(
                "You are producing operator-facing recommendations.\n"
                "- Provide clear descriptions (not summaries) of actions.\n"
                "- Include CLI/API examples as plain strings only when supported by sources; add citations.\n"
                "- Use placeholders like <cluster-mgr>, <admin>, <pass> where needed.\n"
                "- If sources are insufficient, add an Investigate step instead of guessing.\n"
                "- DO NOT include or suggest any internal agent tool names (e.g., re_admin_*, redis_cli_*, loki_*, prometheus_*). The operator cannot run them.\n"
                "- Translate verification and commands to operator-accessible forms only: rladmin, redis-cli, Redis Enterprise Admin API (curl with method/path/payload), or Redis Cloud UI/API steps.\n"
                "- If exact Admin API payloads are unknown, instruct: 'Open an investigation to obtain exact Admin Console steps or REST API payloads. Do not guess API payloads.'\n"
                "- Output must match the Recommendation schema."
            )
        )
        human = HumanMessage(
            content=(
                "Topic (JSON):\n"
                + str(topic)
                + "\n\nInstance Facts (JSON):\n"
                + str(instance)
                + "\n\nAbout the Evidence JSON: It is a verbatim record of upstream tool calls (name, description, args, data).\n"
                "Use only this evidence and any knowledge tool results. Cite sources for actionable examples.\n"
                "Evidence (JSON):\n" + str(evidence)
            )
        )
        if memoize:
            rec = await memoize("rec_worker_synth", structured_llm, [sys, human])
        else:
            rec = await structured_llm.ainvoke([sys, human])
        # rec is already a pydantic model or compatible dict
        if isinstance(rec, dict):
            result = rec
        else:
            # Pydantic model
            result = rec.model_dump()
        # Ensure topic id reflects the input topic, overriding any model-provided value
        result["topic_id"] = topic.get("id", "T?")
        return {**state, "result": result}

    g = StateGraph(RecState)
    g.add_node("llm", llm_node)
    g.add_node("tools", tools_node)
    g.add_node("synth", synth_node)

    g.set_entry_point("llm")
    g.add_conditional_edges("llm", should_continue, {"tools": "tools", "synth": "synth"})
    g.add_edge("tools", "llm")
    g.add_edge("synth", END)

    return g.compile()
