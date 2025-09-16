"""GitHub Issues provider implementation.

This provider connects to GitHub to create, update, and search issues/tickets.
It can work with both public and private repositories.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from ..protocols import Ticket

logger = logging.getLogger(__name__)


class GitHubTicketsProvider:
    """GitHub Issues provider.

    This provider connects to GitHub's REST API to manage issues as tickets.
    It supports creating, updating, and searching issues across repositories.
    """

    def __init__(self, token: str, owner: str, repo: str, base_url: str = "https://api.github.com"):
        if not AIOHTTP_AVAILABLE:
            raise ImportError(
                "aiohttp is required for GitHub provider. Install with: pip install aiohttp"
            )

        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    @property
    def provider_name(self) -> str:
        return f"GitHub Issues ({self.owner}/{self.repo})"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with GitHub authentication."""
        if self.session is None:
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Redis-SRE-Agent/1.0",
            }
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self.session

    async def create_ticket(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Ticket:
        """Create a new GitHub issue."""
        try:
            session = await self._get_session()

            # Prepare issue data
            issue_data = {"title": title, "body": description}

            if labels:
                issue_data["labels"] = labels

            if assignee:
                issue_data["assignees"] = [assignee]

            # Add priority as a label if specified
            if priority:
                priority_label = f"priority:{priority.lower()}"
                if "labels" not in issue_data:
                    issue_data["labels"] = []
                issue_data["labels"].append(priority_label)

            url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues"

            async with session.post(url, json=issue_data) as response:
                if response.status == 201:
                    issue = await response.json()
                    return self._convert_to_ticket(issue)
                else:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error {response.status}: {error_text}")

        except Exception as e:
            logger.error(f"Error creating GitHub issue: {e}")
            raise

    async def update_ticket(self, ticket_id: str, **updates) -> Ticket:
        """Update an existing GitHub issue."""
        try:
            session = await self._get_session()

            # Prepare update data
            update_data = {}

            if "title" in updates:
                update_data["title"] = updates["title"]

            if "description" in updates:
                update_data["body"] = updates["description"]

            if "status" in updates:
                # GitHub uses state: open/closed
                if updates["status"].lower() in ["closed", "resolved", "done"]:
                    update_data["state"] = "closed"
                else:
                    update_data["state"] = "open"

            if "assignee" in updates:
                if updates["assignee"]:
                    update_data["assignees"] = [updates["assignee"]]
                else:
                    update_data["assignees"] = []

            if "labels" in updates:
                update_data["labels"] = updates["labels"]

            url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues/{ticket_id}"

            async with session.patch(url, json=update_data) as response:
                if response.status == 200:
                    issue = await response.json()
                    return self._convert_to_ticket(issue)
                else:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error {response.status}: {error_text}")

        except Exception as e:
            logger.error(f"Error updating GitHub issue {ticket_id}: {e}")
            raise

    async def search_tickets(
        self,
        query: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Ticket]:
        """Search GitHub issues with filters."""
        try:
            session = await self._get_session()

            # Build search query
            search_parts = [f"repo:{self.owner}/{self.repo}"]

            if query:
                search_parts.append(query)

            if status:
                if status.lower() in ["closed", "resolved", "done"]:
                    search_parts.append("state:closed")
                else:
                    search_parts.append("state:open")

            if assignee:
                search_parts.append(f"assignee:{assignee}")

            if labels:
                for label in labels:
                    search_parts.append(f"label:{label}")

            search_query = " ".join(search_parts)

            params = {
                "q": search_query,
                "sort": "updated",
                "order": "desc",
                "per_page": min(limit, 100),  # GitHub API limit
            }

            url = f"{self.base_url}/search/issues"

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    issues = data.get("items", [])
                    return [self._convert_to_ticket(issue) for issue in issues]
                else:
                    error_text = await response.text()
                    logger.error(f"GitHub search error {response.status}: {error_text}")
                    return []

        except Exception as e:
            logger.error(f"Error searching GitHub issues: {e}")
            return []

    async def health_check(self) -> Dict[str, Any]:
        """Check GitHub API connection health."""
        try:
            session = await self._get_session()

            # Test API access by getting repository info
            url = f"{self.base_url}/repos/{self.owner}/{self.repo}"

            async with session.get(url) as response:
                if response.status == 200:
                    repo_data = await response.json()
                    return {
                        "status": "healthy",
                        "provider": self.provider_name,
                        "connected": True,
                        "repository": repo_data.get("full_name"),
                        "private": repo_data.get("private", False),
                        "timestamp": datetime.now().isoformat(),
                    }
                else:
                    error_text = await response.text()
                    return {
                        "status": "unhealthy",
                        "provider": self.provider_name,
                        "error": f"HTTP {response.status}: {error_text}",
                        "connected": False,
                        "timestamp": datetime.now().isoformat(),
                    }

        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "error": str(e),
                "connected": False,
                "timestamp": datetime.now().isoformat(),
            }

    def _convert_to_ticket(self, issue: Dict[str, Any]) -> Ticket:
        """Convert GitHub issue to Ticket object."""
        labels = [label["name"] for label in issue.get("labels", [])]
        assignee = None
        if issue.get("assignee"):
            assignee = issue["assignee"]["login"]

        # Map GitHub state to ticket status
        status = "open"
        if issue.get("state") == "closed":
            status = "closed"

        return Ticket(
            id=str(issue["number"]),
            title=issue["title"],
            description=issue.get("body", ""),
            status=status,
            assignee=assignee,
            labels=labels,
        )

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None


# Helper function to create instances
def create_github_tickets_provider(
    token: str, owner: str, repo: str, base_url: str = "https://api.github.com"
) -> GitHubTicketsProvider:
    """Create a GitHub tickets provider instance."""
    return GitHubTicketsProvider(token, owner, repo, base_url)
