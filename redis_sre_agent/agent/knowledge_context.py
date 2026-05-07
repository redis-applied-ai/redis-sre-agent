"""Knowledge context builders for first-turn system prompt injection."""

import logging
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.knowledge_helpers import (
    get_pinned_documents_helper,
    skills_check_helper,
)
from redis_sre_agent.core.runtime_overrides import (
    EvalKnowledgeBackend,
    get_active_knowledge_backend,
)

logger = logging.getLogger(__name__)

PINNED_CONTEXT_TOOL_KEY = "knowledge.pinned_context"
PINNED_CONTEXT_RETRIEVAL_KIND = "pinned_context"
PINNED_CONTEXT_RETRIEVAL_LABEL = "Pinned context"
STARTUP_SKILLS_TOOL_KEY = "knowledge.startup_skills_check"
STARTUP_SKILLS_RETRIEVAL_KIND = "startup_skills"
STARTUP_SKILLS_RETRIEVAL_LABEL = "Startup skills"


class StartupKnowledgeContext(str):
    """String startup context that also carries internal tool envelopes."""

    internal_tool_envelopes: List[Dict[str, Any]]

    def __new__(
        cls,
        context: str,
        internal_tool_envelopes: Optional[List[Dict[str, Any]]] = None,
    ) -> "StartupKnowledgeContext":
        obj = super().__new__(cls, context)
        obj.internal_tool_envelopes = list(internal_tool_envelopes or [])
        return obj


def merge_internal_tool_envelopes(
    existing: Optional[List[Dict[str, Any]]],
    new: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Append internal envelopes while avoiding duplicate dict entries."""
    merged = list(existing or [])
    for envelope in new or []:
        if envelope not in merged:
            merged.append(envelope)
    return merged


def _skills_toc_lines(skills: List[Dict[str, Any]]) -> List[str]:
    """Render the ADR skills table of contents lines."""
    if not skills:
        return []

    lines = [
        "Skills you know:",
        "Skill inventory rules:",
        "- This startup skill list is inventory only, not proof that you retrieved or followed a skill.",
        "- If a listed skill matches the request, retrieve it with `get_skill` before claiming that you used, followed, or executed it.",
        "- If you use any retrieved skills during your turn, add a note to your answer saying which skill(s) you used.",
    ]
    for skill in skills:
        name = str(skill.get("name", "")).strip() or str(skill.get("title", "")).strip()
        summary = str(skill.get("summary", "")).strip() or str(skill.get("description", "")).strip()
        lines.append(f"- {name}: {summary}")
    return lines


def _pinned_doc_preamble(doc_type: str) -> str:
    normalized = str(doc_type or "").strip().lower()
    if normalized in {"skill", "support_ticket"}:
        label = normalized.replace("_", " ")
        return f"Memorize this pinned {label} by heart and apply it directly when relevant."
    return ""


def _extract_tool_categories(available_tools: Optional[List[Any]] = None) -> List[str]:
    """Return normalized, de-duplicated capability categories for available tools."""
    if not available_tools:
        return []

    categories: set[str] = set()
    for tool in available_tools:
        capability = getattr(tool, "capability", None)
        if capability is None:
            definition = getattr(tool, "definition", None)
            capability = getattr(definition, "capability", None)
        if capability is None:
            metadata = getattr(tool, "metadata", None)
            capability = getattr(metadata, "capability", None)
        if capability is None:
            continue

        normalized = str(getattr(capability, "value", capability)).strip().lower()
        if normalized:
            categories.add(normalized)

    ordered = [
        "diagnostics",
        "metrics",
        "logs",
        "knowledge",
        "tickets",
        "repos",
        "traces",
        "utilities",
    ]
    return [category for category in ordered if category in categories]


def _tool_instruction_lines_for_categories(
    available_tools: Optional[List[Any]] = None,
) -> List[str]:
    """Render ADR tool usage instructions using capability categories."""
    categories = _extract_tool_categories(available_tools)
    if not categories:
        return []

    lines = [
        "Tool usage instructions:",
        "- Only call tools that are available in this session.",
        f"- Available tool categories: {', '.join(categories)}.",
    ]

    category_guidance = {
        "diagnostics": "- Use diagnostics tools for instance-level health checks and Redis command inspection.",
        "metrics": "- Use metrics tools for time-series signals and trend validation.",
        "logs": "- Use logs tools for event timelines and error correlation.",
        "knowledge": "- Use knowledge tools for runbooks, skills, and documentation retrieval.",
        "tickets": "- Use tickets tools for historical incidents and prior remediation patterns. General knowledge search does not include support tickets.",
        "repos": "- Use repos tools for code and configuration investigation.",
        "traces": "- Use traces tools for distributed request-path analysis.",
        "utilities": "- Use utilities tools for safe helper operations (time conversion, lightweight formatting, etc.).",
    }
    for category in categories:
        guidance_line = category_guidance.get(category)
        if guidance_line:
            lines.append(guidance_line)

    if "tickets" in categories:
        lines.append(
            "Support-ticket workflow: when the user asks for support tickets, prior cases, or historical incidents, "
            "use tickets tools instead of general knowledge search. Ask for concrete identifiers "
            "(for example cluster name or cluster host), search with those identifiers, then fetch the best matching ticket."
        )

    return lines


def _build_internal_pinned_context_envelope(
    pinned_docs: List[Dict[str, Any]],
    *,
    version: Optional[str],
    pinned_limit: int,
    pinned_content_char_budget: int,
) -> Optional[Dict[str, Any]]:
    """Build an internal knowledge envelope for pinned startup documents."""
    if not pinned_docs:
        return None

    results: List[Dict[str, Any]] = []
    for document in pinned_docs:
        document_hash = str(document.get("document_hash", "")).strip()
        name = str(document.get("name", "")).strip() or document_hash or "Pinned document"
        results.append(
            {
                "id": document_hash or name,
                "title": name,
                "source": str(document.get("source", "")).strip(),
                "document_hash": document_hash,
                "doc_type": str(document.get("doc_type", "")).strip(),
                "priority": str(document.get("priority", "normal")).strip().lower(),
                "summary": str(document.get("summary", "")).strip(),
                "pinned": True,
                "truncated": bool(document.get("truncated")),
                "retrieval_kind": PINNED_CONTEXT_RETRIEVAL_KIND,
                "retrieval_label": PINNED_CONTEXT_RETRIEVAL_LABEL,
            }
        )

    return {
        "tool_key": PINNED_CONTEXT_TOOL_KEY,
        "name": "pinned_context",
        "description": "Internal pinned-context retrieval recorded during startup grounding.",
        "args": {
            "version": version,
            "limit": pinned_limit,
            "content_char_budget": pinned_content_char_budget,
        },
        "status": "success",
        "data": {
            "results": results,
            "results_count": len(results),
            "retrieval_kind": PINNED_CONTEXT_RETRIEVAL_KIND,
            "retrieval_label": PINNED_CONTEXT_RETRIEVAL_LABEL,
        },
        "summary": f"Loaded {len(results)} pinned document{'s' if len(results) != 1 else ''} into startup context.",
    }


def _build_internal_startup_skills_envelope(
    skills: List[Dict[str, Any]],
    *,
    query: str,
    version: Optional[str],
    skills_limit: int,
) -> Optional[Dict[str, Any]]:
    """Build an internal knowledge envelope for startup skill discovery."""
    if not skills:
        return None

    results: List[Dict[str, Any]] = []
    for skill in skills:
        title = str(skill.get("name", "")).strip() or str(skill.get("title", "")).strip()
        document_hash = str(skill.get("document_hash", "")).strip()
        results.append(
            {
                "id": document_hash or title,
                "title": title or document_hash or "Skill",
                "source": str(skill.get("source", "")).strip(),
                "document_hash": document_hash,
                "doc_type": "skill",
                "summary": str(skill.get("summary", "")).strip(),
                "retrieval_kind": STARTUP_SKILLS_RETRIEVAL_KIND,
                "retrieval_label": STARTUP_SKILLS_RETRIEVAL_LABEL,
            }
        )

    return {
        "tool_key": STARTUP_SKILLS_TOOL_KEY,
        "name": "skills_check",
        "description": "Internal startup skill discovery recorded during grounding.",
        "args": {
            "query": query,
            "limit": skills_limit,
            "offset": 0,
            "version": version,
        },
        "status": "success",
        "data": {
            "results": results,
            "results_count": len(results),
            "retrieval_kind": STARTUP_SKILLS_RETRIEVAL_KIND,
            "retrieval_label": STARTUP_SKILLS_RETRIEVAL_LABEL,
        },
        "summary": f"Loaded {len(results)} startup skill{'s' if len(results) != 1 else ''} into grounding context.",
    }


async def build_startup_knowledge_context(
    query: str,
    version: Optional[str] = "latest",
    pinned_limit: int = 20,
    pinned_content_char_budget: int = 12000,
    skills_limit: int = 20,
    available_tools: Optional[List[Any]] = None,
    knowledge_backend: Optional[EvalKnowledgeBackend] = None,
) -> str:
    """Build first-turn context in ADR order: pinned, skills, tools."""
    sections: List[str] = []
    internal_tool_envelopes: List[Dict[str, Any]] = []
    effective_knowledge_backend = knowledge_backend or get_active_knowledge_backend()

    try:
        if effective_knowledge_backend is not None:
            pinned_result = await effective_knowledge_backend.get_pinned_documents(
                version=version,
                limit=pinned_limit,
                content_char_budget=pinned_content_char_budget,
            )
        else:
            pinned_result = await get_pinned_documents_helper(
                version=version,
                limit=pinned_limit,
                content_char_budget=pinned_content_char_budget,
            )
    except Exception as exc:
        logger.warning("Failed to load pinned documents: %s", exc)
        pinned_result = {"pinned_documents": []}

    pinned_docs = pinned_result.get("pinned_documents") or []
    if pinned_docs:
        pinned_lines = ["Pinned documents:"]
        for document in pinned_docs:
            name = (
                str(document.get("name", "")).strip()
                or str(document.get("document_hash", "")).strip()
            )
            priority = str(document.get("priority", "normal")).strip().lower()
            doc_type = str(document.get("doc_type", "")).strip().lower()
            pinned_lines.append(f"### {name} (priority: {priority})")
            preamble = _pinned_doc_preamble(doc_type)
            if preamble:
                pinned_lines.append(preamble)
            pinned_lines.append(str(document.get("full_content", "")).strip())
        sections.append("\n".join(pinned_lines))

        pinned_envelope = _build_internal_pinned_context_envelope(
            pinned_docs,
            version=version,
            pinned_limit=pinned_limit,
            pinned_content_char_budget=pinned_content_char_budget,
        )
        if pinned_envelope:
            internal_tool_envelopes.append(pinned_envelope)

    try:
        if effective_knowledge_backend is not None:
            skills_result = await effective_knowledge_backend.skills_check(
                query=query,
                limit=skills_limit,
                offset=0,
                version=version,
            )
        else:
            skills_result = await skills_check_helper(
                query=query,
                limit=skills_limit,
                offset=0,
                version=version,
            )
    except Exception as exc:
        logger.warning("Failed to run startup skills check: %s", exc)
        skills_result = {"skills": []}

    skills_lines = _skills_toc_lines(skills_result.get("skills") or [])
    if skills_lines:
        sections.append("\n".join(skills_lines))
        skills_envelope = _build_internal_startup_skills_envelope(
            skills_result.get("skills") or [],
            query=query,
            version=version,
            skills_limit=skills_limit,
        )
        if skills_envelope:
            internal_tool_envelopes.append(skills_envelope)

    tool_lines = _tool_instruction_lines_for_categories(available_tools)
    if tool_lines:
        sections.append("\n".join(tool_lines))

    return StartupKnowledgeContext(
        "\n\n".join(section for section in sections if section.strip()),
        internal_tool_envelopes=internal_tool_envelopes,
    )
