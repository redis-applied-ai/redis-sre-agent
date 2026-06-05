"""Citation formatting helpers.

Knowledge citations are now exposed to clients as structured task/thread data.
The message payload helpers remain for legacy persisted transcript rows.
"""

from typing import Any, Dict, List, Optional

from redis_sre_agent.agent.helpers import build_citation_groups


def should_include_citations(search_results: Optional[List[Dict[str, Any]]]) -> bool:
    """Determine if citations should be included in the thread.

    Args:
        search_results: List of search results from knowledge base queries

    Returns:
        True if there are citations to include, False otherwise
    """
    if search_results is None:
        return False
    return len(search_results) > 0


def format_citation_message(search_results: Optional[List[Dict[str, Any]]]) -> str:
    """Format search results as a citation message for the conversation history.

    Creates a system message that lists the sources used in the previous response,
    including document hashes that can be used with get_all_fragments to retrieve
    more content.

    Args:
        search_results: List of search results from knowledge base queries.
            Each result should have: title, source, document_hash, and optionally score.

    Returns:
        Formatted citation message string, or empty string if no results.
    """
    if not should_include_citations(search_results):
        return ""

    lines = ["**Sources for previous response**"]
    lines.extend(_format_citation_lines(list(search_results or [])))
    return "\n".join(lines)


def _format_citation_lines(citations: List[Dict[str, Any]]) -> List[str]:
    """Format citation entries into display lines shared by message renderers."""
    lines: List[str] = []
    for result in citations:
        title = result.get("title", "Untitled")
        source = result.get("source", "Unknown source")
        doc_hash = result.get("document_hash", "")
        score = result.get("score")

        if score is not None:
            lines.append(f'• "{title}" ({source}) [hash:{doc_hash}] - relevance: {score}')
        else:
            lines.append(f'• "{title}" ({source}) [hash:{doc_hash}]')

    return lines


def format_citation_group_message(citation_group: Dict[str, Any]) -> str:
    """Format one citation group as a system message body."""
    citations = list(citation_group.get("citations") or [])
    if not citations:
        return ""

    lines = [f"**{citation_group.get('label', 'Sources')}**"]
    lines.extend(_format_citation_lines(citations))
    return "\n".join(lines)


def build_citation_message_payloads(
    search_results: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Build separate system-message payloads for each citation group."""
    if not should_include_citations(search_results):
        return []

    payloads: List[Dict[str, Any]] = []
    for citation_group in build_citation_groups(list(search_results or [])):
        payloads.append(
            {
                "content": format_citation_group_message(citation_group),
                "metadata": {
                    "message_type": "citations",
                    "citation_group": citation_group["group_key"],
                    "citation_group_label": citation_group["label"],
                    "citations": citation_group["citations"],
                    "count": citation_group["count"],
                },
            }
        )
    return payloads


def build_citation_group_payloads(
    search_results: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Build structured citation groups for API/task metadata."""
    if not should_include_citations(search_results):
        return []

    return [
        {
            "group_key": citation_group["group_key"],
            "label": citation_group["label"],
            "citations": citation_group["citations"],
            "count": citation_group["count"],
        }
        for citation_group in build_citation_groups(list(search_results or []))
    ]


def extract_citation_groups_from_task_result(
    result: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract structured citation groups from current or legacy task results."""
    if not isinstance(result, dict):
        return []

    citation_groups = result.get("citation_groups")
    if isinstance(citation_groups, list):
        return citation_groups

    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        metadata_citation_groups = metadata.get("citation_groups")
        if isinstance(metadata_citation_groups, list):
            return metadata_citation_groups

    response = result.get("response")
    if isinstance(response, dict):
        response_citation_groups = response.get("citation_groups")
        if isinstance(response_citation_groups, list):
            return response_citation_groups

        search_results = response.get("search_results")
        if isinstance(search_results, list):
            return build_citation_group_payloads(search_results)

    search_results = result.get("search_results")
    if isinstance(search_results, list):
        return build_citation_group_payloads(search_results)

    return []
