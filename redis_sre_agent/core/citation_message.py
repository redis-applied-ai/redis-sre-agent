"""Citation message formatting for thread history.

Formats knowledge base search results as system messages that become part of
the conversation history, allowing the LLM to see which sources were used
in previous responses.
"""

from typing import Any, Dict, List, Optional


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

    for result in search_results:
        title = result.get("title", "Untitled")
        source = result.get("source", "Unknown source")
        doc_hash = result.get("document_hash", "")
        score = result.get("score")

        # Format the citation line
        if score is not None:
            line = f'• "{title}" ({source}) [hash:{doc_hash}] - relevance: {score}'
        else:
            line = f'• "{title}" ({source}) [hash:{doc_hash}]'

        lines.append(line)

    return "\n".join(lines)
