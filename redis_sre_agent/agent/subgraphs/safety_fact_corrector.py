"""
Safety/Fact Corrector subgraph.

This post-processing subgraph minimally edits the agent's final response to correct
safety issues and factual errors. It is bounded, advisory, and never restarts the
main analysis. It may use a small toolbelt (knowledge search, URL HEAD, calculator,
time/date) with a strict step budget.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from opentelemetry import trace

from ..helpers import log_preflight_messages, sanitize_messages_for_llm
from ..models import CorrectionResult

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class CorrectorState(TypedDict, total=False):
    messages: List[BaseMessage]
    budget: int
    response_text: str
    instance: Dict[str, Any]
    result: Dict[str, Any]


def build_safety_fact_corrector(
    base_llm,
    tool_adapters: List[Any],
    *,
    max_tool_steps: int = 2,
    memoize=None,
):
    """Build a compiled subgraph that edits a response for safety/fact accuracy.

    The LLM may call only the provided tool_adapters (should be limited to
    knowledge_* search and utilities_* like http_head, calculator, date/time).
    """

    tool_node = ToolNode(tool_adapters)

    async def llm_node(state: CorrectorState) -> CorrectorState:
        messages = sanitize_messages_for_llm(state.get("messages", []))
        log_preflight_messages(messages, label="Corrector preflight LLM", logger=logger)
        if memoize:
            resp = await memoize("corrector_llm", base_llm, messages)
        else:
            resp = await base_llm.ainvoke(messages)
        out: CorrectorState = {
            "messages": messages + [resp],
            "budget": int(state.get("budget", max_tool_steps)),
            "response_text": state.get("response_text", ""),
            "instance": state.get("instance") or {},
        }
        return out

    async def tools_node(state: CorrectorState) -> CorrectorState:
        prev = state.get("messages", [])
        log_preflight_messages(prev, label="Corrector preflight ToolNode", logger=logger)
        out = await tool_node.ainvoke({"messages": prev})
        out_msgs = out.get("messages", [])
        from langchain_core.messages import ToolMessage as _TM  # noqa: N814

        delta = [m for m in out_msgs if isinstance(m, _TM)]
        messages = prev + delta if delta else prev
        budget = max(0, int(state.get("budget", max_tool_steps)) - 1)
        return {
            "messages": messages,
            "budget": budget,
            "response_text": state.get("response_text", ""),
            "instance": state.get("instance") or {},
        }

    def should_continue(state: CorrectorState) -> str:
        msgs = state.get("messages", [])
        last_ai: Optional[AIMessage] = None
        for m in reversed(msgs):
            if isinstance(m, AIMessage):
                last_ai = m
                break
        has_calls = bool(getattr(last_ai, "tool_calls", None))
        budget_left = int(state.get("budget", max_tool_steps)) > 0
        return "tools" if (has_calls and budget_left) else "synth"

    async def synth_node(state: CorrectorState) -> CorrectorState:
        # Final strict edit-only synthesis
        structured_llm = base_llm.with_structured_output(CorrectionResult)
        sys = SystemMessage(
            content=(
                "You are a Redis SRE Corrector. Edit ONLY the given response to fix safety and factual errors.\n"
                "- Do not add new topics or steps.\n"
                "- Remove fabricated commands; prefer documented rladmin, redis-cli, or Admin REST API curl examples.\n"
                "- If you cannot confirm an exact command/API syntax via knowledge search, remove it and add a short caution.\n"
                "- If the instance appears persistent, do NOT recommend eviction or destructive changes; remove unsafe steps.\n"
                "- If URLs are broken, remove or replace with a validated doc URL.\n"
                "Return the edited text and a short list of edits applied."
            )
        )
        human = HumanMessage(
            content=(
                "Original response to correct (verbatim):\n"
                + str(state.get("response_text", ""))
                + "\n\nInstance facts (JSON):\n"
                + str(state.get("instance") or {})
            )
        )
        if memoize:
            rec = await memoize("corrector_synth", structured_llm, [sys, human])
        else:
            rec = await structured_llm.ainvoke([sys, human])
        result = rec if isinstance(rec, dict) else rec.model_dump()
        return {**state, "result": result}

    g = StateGraph(CorrectorState)

    # Lightweight OTel wrapper to trace per-node execution
    def _trace_node(node_name: str):
        def _decorator(fn):
            async def _wrapped(state: CorrectorState) -> CorrectorState:
                with tracer.start_as_current_span(
                    "langgraph.node",
                    attributes={
                        "langgraph.graph": "corrector",
                        "langgraph.node": node_name,
                    },
                ):
                    return await fn(state)

            return _wrapped

        return _decorator

    g.add_node("llm", _trace_node("llm")(llm_node))
    g.add_node("tools", _trace_node("tools")(tools_node))
    g.add_node("synth", _trace_node("synth")(synth_node))

    g.set_entry_point("llm")
    g.add_conditional_edges("llm", should_continue, {"tools": "tools", "synth": "synth"})
    g.add_edge("tools", "llm")
    g.add_edge("synth", END)

    return g.compile()
