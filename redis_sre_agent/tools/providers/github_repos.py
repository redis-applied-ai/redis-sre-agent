"""GitHub Repositories provider implementation.

This provider connects to GitHub to access repository information and search code.
It can help the agent understand what repositories use a Redis instance.
"""

import base64
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from ..protocols import Repository

logger = logging.getLogger(__name__)


class GitHubReposProvider:
    """GitHub Repositories provider.

    This provider connects to GitHub's REST API to access repository information,
    search code, and analyze repository contents for Redis usage patterns.
    """

    def __init__(self, token: str, organization: Optional[str] = None, base_url: str = "https://api.github.com"):
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required for GitHub provider. Install with: pip install aiohttp")

        self.token = token
        self.organization = organization
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    @property
    def provider_name(self) -> str:
        org_part = f" ({self.organization})" if self.organization else ""
        return f"GitHub Repositories{org_part}"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with GitHub authentication."""
        if self.session is None:
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Redis-SRE-Agent/1.0"
            }
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self.session

    async def list_repositories(self, organization: Optional[str] = None) -> List[Repository]:
        """List GitHub repositories."""
        try:
            session = await self._get_session()

            org = organization or self.organization
            repositories = []

            if org:
                # List organization repositories
                url = f"{self.base_url}/orgs/{org}/repos"
                params = {"type": "all", "sort": "updated", "per_page": 100}
            else:
                # List user repositories
                url = f"{self.base_url}/user/repos"
                params = {"type": "all", "sort": "updated", "per_page": 100}

            page = 1
            while len(repositories) < 500:  # Reasonable limit
                params["page"] = page

                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        repos = await response.json()
                        if not repos:  # No more pages
                            break

                        for repo in repos:
                            languages = await self._get_repository_languages(repo["full_name"])

                            repository = Repository(
                                name=repo["full_name"],
                                url=repo["html_url"],
                                default_branch=repo.get("default_branch", "main"),
                                languages=languages
                            )
                            repositories.append(repository)

                        page += 1
                    else:
                        error_text = await response.text()
                        logger.error(f"GitHub API error {response.status}: {error_text}")
                        break

            return repositories

        except Exception as e:
            logger.error(f"Error listing GitHub repositories: {e}")
            return []

    async def search_code(
        self,
        query: str,
        repositories: Optional[List[str]] = None,
        file_extensions: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search code across GitHub repositories."""
        try:
            session = await self._get_session()

            # Build search query
            search_parts = [query]

            if repositories:
                for repo in repositories:
                    search_parts.append(f"repo:{repo}")
            elif self.organization:
                search_parts.append(f"org:{self.organization}")

            if file_extensions:
                for ext in file_extensions:
                    search_parts.append(f"extension:{ext}")

            search_query = " ".join(search_parts)

            params = {
                "q": search_query,
                "sort": "indexed",
                "order": "desc",
                "per_page": min(limit, 100)  # GitHub API limit
            }

            url = f"{self.base_url}/search/code"

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get("items", [])

                    results = []
                    for item in items:
                        result = {
                            "repository": item["repository"]["full_name"],
                            "file_path": item["path"],
                            "file_name": item["name"],
                            "url": item["html_url"],
                            "score": item.get("score", 0),
                            "snippet": await self._get_file_snippet(
                                item["repository"]["full_name"],
                                item["path"],
                                query
                            )
                        }
                        results.append(result)

                    return results
                else:
                    error_text = await response.text()
                    logger.error(f"GitHub code search error {response.status}: {error_text}")
                    return []

        except Exception as e:
            logger.error(f"Error searching GitHub code: {e}")
            return []

    async def get_file_content(self, repository: str, file_path: str, branch: str = "main") -> str:
        """Get content of a specific file from GitHub."""
        try:
            session = await self._get_session()

            url = f"{self.base_url}/repos/{repository}/contents/{file_path}"
            params = {"ref": branch}

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # GitHub returns base64-encoded content
                    if data.get("encoding") == "base64":
                        content = base64.b64decode(data["content"]).decode("utf-8")
                        return content
                    else:
                        return data.get("content", "")
                else:
                    error_text = await response.text()
                    logger.error(f"GitHub file content error {response.status}: {error_text}")
                    return ""

        except Exception as e:
            logger.error(f"Error getting GitHub file content: {e}")
            return ""

    async def health_check(self) -> Dict[str, Any]:
        """Check GitHub API connection health."""
        try:
            session = await self._get_session()

            # Test API access by getting user info
            url = f"{self.base_url}/user"

            async with session.get(url) as response:
                if response.status == 200:
                    user_data = await response.json()
                    return {
                        "status": "healthy",
                        "provider": self.provider_name,
                        "connected": True,
                        "user": user_data.get("login"),
                        "rate_limit_remaining": response.headers.get("X-RateLimit-Remaining"),
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    error_text = await response.text()
                    return {
                        "status": "unhealthy",
                        "provider": self.provider_name,
                        "error": f"HTTP {response.status}: {error_text}",
                        "connected": False,
                        "timestamp": datetime.now().isoformat()
                    }

        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "error": str(e),
                "connected": False,
                "timestamp": datetime.now().isoformat()
            }

    async def _get_repository_languages(self, repo_full_name: str) -> List[str]:
        """Get programming languages used in a repository."""
        try:
            session = await self._get_session()

            url = f"{self.base_url}/repos/{repo_full_name}/languages"

            async with session.get(url) as response:
                if response.status == 200:
                    languages_data = await response.json()
                    return list(languages_data.keys())
                else:
                    return []

        except Exception as e:
            logger.debug(f"Error getting languages for {repo_full_name}: {e}")
            return []

    async def _get_file_snippet(self, repository: str, file_path: str, query: str) -> str:
        """Get a snippet of file content around the search query."""
        try:
            content = await self.get_file_content(repository, file_path)
            if not content:
                return ""

            lines = content.split("\n")
            query_lower = query.lower()

            # Find lines containing the query
            matching_lines = []
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    # Include context lines (2 before, 2 after)
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context_lines = lines[start:end]

                    snippet = "\n".join(f"{start + j + 1}: {context_lines[j]}" for j in range(len(context_lines)))
                    matching_lines.append(snippet)

                    if len(matching_lines) >= 3:  # Limit snippets
                        break

            return "\n\n".join(matching_lines)

        except Exception as e:
            logger.debug(f"Error getting file snippet: {e}")
            return ""

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None


# Helper function to create instances
def create_github_repos_provider(
    token: str,
    organization: Optional[str] = None,
    base_url: str = "https://api.github.com"
) -> GitHubReposProvider:
    """Create a GitHub repositories provider instance."""
    return GitHubReposProvider(token, organization, base_url)
