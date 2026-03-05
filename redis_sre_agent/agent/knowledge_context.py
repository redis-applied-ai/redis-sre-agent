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
    lines = ["Skills you know:"]
    if not skills:
        lines.append("- (none)")
        return lines

    for skill in skills:
        name = str(skill.get("name", "")).strip() or str(skill.get("title", "")).strip()
        summary = str(skill.get("summary", "")).strip()
        lines.append(f"- {name}: {summary}")
    return lines


def _tool_instruction_lines() -> List[str]:
    """Render explicit ADR tool usage instructions."""
    return [
        "Tool usage instructions:",
        '- get-skill("<skill_name>")',
        '- skills-check("<query>")',
        '- search-support-tickets("<query>")',
        '- get-support-ticket("<id>")',
    ]


async def build_startup_knowledge_context(
    query: str,
    version: Optional[str] = "latest",
    pinned_limit: int = 20,
    pinned_content_char_budget: int = 12000,
    skills_limit: int = 20,
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
    pinned_lines = ["Pinned documents:"]
    if not pinned_docs:
        pinned_lines.append("- (none)")
    else:
        for document in pinned_docs:
            name = (
                str(document.get("name", "")).strip()
                or str(document.get("document_hash", "")).strip()
            )
            priority = str(document.get("priority", "normal")).strip().lower()
            pinned_lines.append(f"### {name} (priority: {priority})")
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

    sections.append("\n".join(_skills_toc_lines(skills_result.get("skills") or [])))
    sections.append("\n".join(_tool_instruction_lines()))
    return "\n\n".join(section for section in sections if section.strip())
