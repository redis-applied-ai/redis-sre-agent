"""Knowledge context builders for first-turn system prompt injection."""

import logging
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.knowledge_helpers import (
    get_pinned_documents_helper,
    skills_check_helper,
)

logger = logging.getLogger(__name__)


def _skills_toc_lines(skills: List[Dict[str, Any]]) -> List[str]:
    """Render the ADR skills table of contents lines."""
    if not skills:
        return []

    lines = ["Skills you know:"]
    for skill in skills:
        name = str(skill.get("name", "")).strip() or str(skill.get("title", "")).strip()
        summary = str(skill.get("summary", "")).strip()
        lines.append(f"- {name}: {summary}")
    return lines


def _pinned_doc_preamble(doc_type: str) -> str:
    normalized = str(doc_type or "").strip().lower()
    if normalized in {"skill", "support_ticket"}:
        label = normalized.replace("_", " ")
        return f"Memorize this pinned {label} by heart and apply it directly when relevant."
    return ""


def _resolve_tool_name(available_tool_names: Optional[List[str]], operation: str) -> str:
    """Resolve full tool name for an operation when hashed provider names are present."""
    if not available_tool_names:
        return operation

    suffix = f"_{operation}"
    for tool_name in available_tool_names:
        if tool_name == operation or tool_name.endswith(suffix):
            return tool_name
    return operation


def _tool_instruction_lines_with_names(
    available_tool_names: Optional[List[str]] = None,
) -> List[str]:
    """Render explicit ADR tool usage instructions using concrete tool names."""
    get_skill_name = _resolve_tool_name(available_tool_names, "get_skill")
    skills_check_name = _resolve_tool_name(available_tool_names, "skills_check")
    search_tickets_name = _resolve_tool_name(available_tool_names, "search_support_tickets")
    get_ticket_name = _resolve_tool_name(available_tool_names, "get_support_ticket")
    return [
        "Tool usage instructions:",
        f'- {get_skill_name}("<skill_name>")',
        f'- {skills_check_name}("<query>")',
        f'- {search_tickets_name}("<query>")',
        f'- {get_ticket_name}("<id>")',
        (
            "Support-ticket workflow: when investigating incidents, ask for concrete identifiers "
            "(for example cluster name or cluster host), search tickets with those identifiers, "
            "then fetch the best matching ticket by id."
        ),
    ]


async def build_startup_knowledge_context(
    query: str,
    version: Optional[str] = "latest",
    pinned_limit: int = 20,
    pinned_content_char_budget: int = 12000,
    skills_limit: int = 20,
    available_tool_names: Optional[List[str]] = None,
) -> str:
    """Build first-turn context in ADR order: pinned, skills, tools."""
    sections: List[str] = []

    try:
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

    try:
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

    if pinned_docs or skills_lines:
        sections.append("\n".join(_tool_instruction_lines_with_names(available_tool_names)))

    return "\n\n".join(section for section in sections if section.strip())
