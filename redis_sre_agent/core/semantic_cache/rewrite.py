"""Mid-conversation query rewriting (contextualization) for the cache key.

Resolves a context-dependent follow-up ("what about for 7.2?") into a standalone
question so it can be matched/stored on its own. This is *contextualization*, not
paraphrase-matching — LangCache handles paraphrases semantically (design §F).

* **First-turn** queries (no conversation history) are used verbatim — zero LLM
  cost on the common path.
* **Mid-conversation** queries are rewritten via the cheapest ``nano`` tier.
* **Fail open**: any error returns the raw query unchanged.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from redis_sre_agent.core.llm_helpers import create_nano_llm

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM_PROMPT = (
    "You rewrite a user's latest question into a fully standalone question using "
    "the prior conversation for context. Output ONLY the rewritten question, no "
    "preamble.\n"
    "Hard rules:\n"
    "- Preserve verbatim, never paraphrase: version numbers (7.8, latest), config "
    "directives (maxmemory, maxmemory-policy, appendonly), commands (CONFIG SET, "
    "BGREWRITEAOF), error/log tokens (MISCONF, OOM), metric names, identifiers, "
    "paths, flags, and quoted strings.\n"
    "- NEVER introduce a version, environment, or edition the user did not state.\n"
    "- If the question is already self-contained, return it unchanged."
)


def _conversation_to_text(conversation_history: List[BaseMessage]) -> str:
    lines: List[str] = []
    for message in conversation_history:
        role = getattr(message, "type", "message")
        content = getattr(message, "content", "")
        if isinstance(content, str) and content.strip():
            lines.append(f"{role}: {content.strip()}")
    return "\n".join(lines)


async def rewrite_query(
    query: str,
    conversation_history: Optional[List[BaseMessage]] = None,
) -> str:
    """Return a standalone form of ``query`` for use as the cache key.

    First-turn queries (no history) are returned unchanged. Mid-conversation
    queries are rewritten via the nano LLM; on any error the raw query is
    returned (fail open).
    """
    if not conversation_history:
        return query

    try:
        llm = create_nano_llm()
        messages = [
            SystemMessage(content=_REWRITE_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Conversation so far:\n{_conversation_to_text(conversation_history)}\n\n"
                    f"Latest question: {query}\n\nStandalone question:"
                )
            ),
        ]
        result = await llm.ainvoke(messages)
        rewritten = getattr(result, "content", "")
        if isinstance(rewritten, str) and rewritten.strip():
            return rewritten.strip()
        return query
    except Exception as exc:
        logger.warning("semantic-cache query rewrite failed (using raw query): %s", exc)
        return query
