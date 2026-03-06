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


def _extract_tool_categories(available_tools: Optional[List[Any]] = None) -> List[str]:
    """Return normalized, de-duplicated capability categories for available tools."""
    if not available_tools:
        return []

    categories: set[str] = set()
    for tool in available_tools:
        capability = getattr(tool, "capability", None)
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
        "tickets": "- Use tickets tools for historical incidents and prior remediation patterns.",
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
            "Support-ticket workflow: ask for concrete identifiers (for example cluster name or cluster host), "
            "search with those identifiers, then fetch the best matching ticket."
        )

    return lines


async def build_startup_knowledge_context(
    query: str,
    version: Optional[str] = "latest",
    pinned_limit: int = 20,
    pinned_content_char_budget: int = 12000,
    skills_limit: int = 20,
    available_tools: Optional[List[Any]] = None,
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
        tool_lines = _tool_instruction_lines_for_categories(available_tools)
        if tool_lines:
            sections.append("\n".join(tool_lines))

    return "\n\n".join(section for section in sections if section.strip())
